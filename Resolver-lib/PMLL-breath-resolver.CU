// pmll_breath_resonator.cu
// A minimal PMLL-inspired "breath" resonator with a persistent CUDA kernel.
//
// Rhythm: inhale → interpret → exhale → pulse
// - Gathers entropy (clock64, thread coords, host nonce)
// - Computes a collective SHA-256 over state
// - Emits a LogEntry into a host-visible ring buffer
// - Listens for host commands (STOP, MARK, SET_RATE)
//
// This is a pedagogical scaffold. Safe to extend with your PMLL nodes,
// GPU integrity passes, and signed provenance.

// ---------- Includes ----------
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <atomic>
#include <chrono>
#include <thread>
#include <vector>
#include <csignal>

// ---------- Tunables ----------
static constexpr int   TPB                 = 256;           // threads per block
static constexpr int   BLOCKS              = 1;             // persistent single-CTA for simplicity
static constexpr size_t LOG_CAPACITY       = 32768;         // ring entries
static constexpr uint64_t DEFAULT_SLEEP_NS = 2'000'000ULL;  // ~2 ms between breaths

// ---------- Commands ----------
enum : uint32_t {
    CMD_NONE    = 0,
    CMD_STOP    = 1,
    CMD_MARK    = 2,   // places a host-provided marker into the next entry
    CMD_SET_HZ  = 3,   // sets target breath period via nanoseconds in param
};

// ---------- Device/Host shared structs ----------
struct BreathCommand {
    std::atomic<uint32_t> opcode;   // host writes, device reads
    std::atomic<uint64_t> param;    // generic parameter (e.g., ns period)
    std::atomic<uint64_t> marker;   // user marker to stamp into log
};

struct LogEntry {
    uint64_t   seq;                 // monotonically increasing breath index
    uint64_t   clk;                 // clock64() snapshot (device ticks)
    uint64_t   entropy_mix;         // mixed entropy
    uint32_t   digest[8];           // SHA-256 of state blob
    uint64_t   host_nonce;          // host-provided nonce at that time
    uint32_t   gridDimX, blockDimX, threadCount;
    uint32_t   marker_seen;         // nonzero if a MARK was applied
};

struct ResonatorState {
    std::atomic<uint64_t> write_idx; // ring write cursor
    uint64_t              capacity;  // ring capacity
    uint64_t              host_nonce;
    std::atomic<uint64_t> breaths;   // total breaths emitted
    std::atomic<uint64_t> dropped;   // count of overwrites (if reader lags)
    std::atomic<uint64_t> ns_period; // target nanoseconds between pulses
};

// ---------- SHA-256 (compact, device-capable) ----------
__device__ __host__ inline uint32_t rotr(uint32_t x, uint32_t n) {
    return (x >> n) | (x << (32 - n));
}

__device__ inline void sha256_transform(uint32_t state[8], const uint8_t block[64]) {
    static const uint32_t K[64] = {
        0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
        0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
        0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
        0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
        0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
        0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
        0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
        0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u
    };

    uint32_t w[64];
#pragma unroll
    for (int i = 0; i < 16; ++i) {
        w[i] = (uint32_t)block[i * 4 + 0] << 24 |
               (uint32_t)block[i * 4 + 1] << 16 |
               (uint32_t)block[i * 4 + 2] << 8  |
               (uint32_t)block[i * 4 + 3];
    }
#pragma unroll
    for (int i = 16; i < 64; ++i) {
        uint32_t s0 = rotr(w[i-15], 7) ^ rotr(w[i-15],18) ^ (w[i-15] >> 3);
        uint32_t s1 = rotr(w[i-2],17) ^ rotr(w[i-2],19) ^ (w[i-2] >> 10);
        w[i] = w[i-16] + s0 + w[i-7] + s1;
    }

    uint32_t a=state[0],b=state[1],c=state[2],d=state[3];
    uint32_t e=state[4],f=state[5],g=state[6],h=state[7];

#pragma unroll
    for (int i = 0; i < 64; ++i) {
        uint32_t S1 = rotr(e,6) ^ rotr(e,11) ^ rotr(e,25);
        uint32_t ch = (e & f) ^ ((~e) & g);
        uint32_t temp1 = h + S1 + ch + K[i] + w[i];
        uint32_t S0 = rotr(a,2) ^ rotr(a,13) ^ rotr(a,22);
        uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
        uint32_t temp2 = S0 + maj;

        h = g;
        g = f;
        f = e;
        e = d + temp1;
        d = c;
        c = b;
        b = a;
        a = temp1 + temp2;
    }

    state[0] += a; state[1] += b; state[2] += c; state[3] += d;
    state[4] += e; state[5] += f; state[6] += g; state[7] += h;
}

__device__ inline void sha256(const uint8_t* data, size_t len, uint32_t out[8]) {
    // Initial hash values
    out[0]=0x6a09e667u; out[1]=0xbb67ae85u; out[2]=0x3c6ef372u; out[3]=0xa54ff53au;
    out[4]=0x510e527fu; out[5]=0x9b05688cu; out[6]=0x1f83d9abu; out[7]=0x5be0cd19u;

    uint8_t block[64];
    size_t full = len & ~((size_t)63);
    for (size_t i = 0; i < full; i += 64) {
        sha256_transform(out, data + i);
    }

    size_t rem = len - full;
    memset(block, 0, 64);
    if (rem) memcpy(block, data + full, rem);
    block[rem] = 0x80;
    uint64_t bit_len = (uint64_t)len * 8ull;

    if (rem >= 56) {
        sha256_transform(out, block);
        memset(block, 0, 64);
    }
    // append length
    for (int i = 0; i < 8; ++i) block[56 + i] = (uint8_t)(bit_len >> (56 - 8*i));
    sha256_transform(out, block);
}

// ---------- Utility: atomic fetch-add for uint64 on device ----------
__device__ inline uint64_t d_atomic_fetch_add_u64(unsigned long long* addr, uint64_t val){
    return atomicAdd(addr, (unsigned long long)val);
}

// ---------- Global device pointers ----------
__device__ ResonatorState* g_state = nullptr;
__device__ BreathCommand*  g_cmd   = nullptr;
__device__ LogEntry*       g_log   = nullptr;

// ---------- Persistent kernel ----------
__global__ void breath_kernel() {
    // Single persistent block assumed.
    const uint32_t tid = threadIdx.x;
    const uint32_t tcount = blockDim.x;

    auto* state = g_state;
    auto* cmd   = g_cmd;
    auto* log   = g_log;

    // local cache
    uint64_t ns_period = state->ns_period.load(std::memory_order_relaxed);

    // collective loop
    while (true) {
        // ------ inhale: gather entropy
        uint64_t clk = clock64();
        uint64_t entropy = clk ^ (uint64_t)tid ^ ((uint64_t)blockIdx.x << 32);
        // scramble
        entropy ^= (entropy << 13); entropy ^= (entropy >> 7); entropy ^= (entropy << 17);

        // reduce entropy across threads via XOR
        __shared__ uint64_t s_entropy;
        if (tid == 0) s_entropy = 0;
        __syncthreads();
        atomicXor((unsigned long long*)&s_entropy, (unsigned long long)entropy);
        __syncthreads();

        // ------ interpret: build a small state blob and hash
        // per-thread local slice
        struct Slice {
            uint64_t clk, ent, host_nonce, seq_hint;
            uint32_t tid, tcount, blk, grd;
        } slice;

        slice.clk        = clk;
        slice.ent        = s_entropy;
        slice.host_nonce = state->host_nonce;
        slice.seq_hint   = state->breaths.load(std::memory_order_relaxed);
        slice.tid        = tid;
        slice.tcount     = tcount;
        slice.blk        = blockIdx.x;
        slice.grd        = gridDim.x;

        uint32_t digest[8];
        sha256(reinterpret_cast<const uint8_t*>(&slice), sizeof(slice), digest);

        // reduce digests via XOR into thread 0
        __shared__ uint32_t s_digest[8];
        if (tid < 8) s_digest[tid] = 0;
        __syncthreads();
        if (tid < 8) atomicXor((unsigned int*)&s_digest[tid], digest[tid]);
        __syncthreads();

        // ------ command handling (thread 0)
        if (tid == 0) {
            // read command once
            uint32_t opcode = cmd->opcode.load(std::memory_order_acquire);
            uint32_t marker_seen = 0;

            if (opcode == CMD_SET_HZ) {
                ns_period = cmd->param.load(std::memory_order_relaxed);
                state->ns_period.store(ns_period, std::memory_order_relaxed);
                cmd->opcode.store(CMD_NONE, std::memory_order_release);
            } else if (opcode == CMD_MARK) {
                marker_seen = 1;
                // will embed marker in log entry below
                cmd->opcode.store(CMD_NONE, std::memory_order_release);
            } else if (opcode == CMD_STOP) {
                // write a final entry noting stop and exit
                uint64_t w = state->write_idx.load(std::memory_order_relaxed);
                uint64_t pos = w % state->capacity;

                LogEntry e{};
                e.seq          = state->breaths.load(std::memory_order_relaxed);
                e.clk          = clk;
                e.entropy_mix  = s_entropy ^ 0x5A5A5A5A5A5A5A5Aull;
                for (int i=0;i<8;++i) e.digest[i] = s_digest[i];
                e.host_nonce   = state->host_nonce;
                e.gridDimX     = gridDim.x;
                e.blockDimX    = blockDim.x;
                e.threadCount  = blockDim.x * gridDim.x;
                e.marker_seen  = 0xDEADCAFEu;

                log[pos] = e;
                __threadfence_system();

                state->write_idx.store(w + 1, std::memory_order_relaxed);
                state->breaths.store(e.seq + 1, std::memory_order_relaxed);
                return; // stop kernel
            }

            // ------ exhale: write log entry
            uint64_t w = state->write_idx.load(std::memory_order_relaxed);
            uint64_t pos = w % state->capacity;

            LogEntry e{};
            e.seq          = state->breaths.load(std::memory_order_relaxed);
            e.clk          = clk;
            e.entropy_mix  = s_entropy;
            for (int i=0;i<8;++i) e.digest[i] = s_digest[i];
            e.host_nonce   = state->host_nonce ^ cmd->marker.load(std::memory_order_relaxed);
            e.gridDimX     = gridDim.x;
            e.blockDimX    = blockDim.x;
            e.threadCount  = blockDim.x * gridDim.x;
            e.marker_seen  = marker_seen;

            log[pos] = e;
            __threadfence_system();

            // advance ring
            state->write_idx.store(w + 1, std::memory_order_relaxed);
            state->breaths.store(e.seq + 1, std::memory_order_relaxed);

            if ((w + 1) - state->capacity > 0) {
                // naive overwrite detection
                state->dropped.fetch_add(1, std::memory_order_relaxed);
            }
        }

        __syncthreads();

        // ------ pulse: simple timed spacing using clock64 spin
        // Convert ns_period to approximate cycles. Assume 1.0 GHz if unknown:
        // We emulate with a short sleep on the host; on device, a small spin
        // to avoid watchdog triggering (keep it tiny).
        // Minimal spin:
        uint64_t goal = clock64() + 50000; // small spin (~tens of microseconds)
        while (clock64() < goal) { /* spin */ }
    }
}

// ---------- Host utility ----------
static std::atomic<bool> g_interrupted{false};
static void on_sigint(int){ g_interrupted.store(true); }

template <typename T>
static void checkCuda(T err, const char* msg){
    if (err != cudaSuccess) {
        fprintf(stderr, "CUDA error at %s: %s\n", msg, cudaGetErrorString((cudaError_t)err));
        std::exit(1);
    }
}

int main() {
    std::signal(SIGINT, on_sigint);

    // Allocate unified memory so host sees updates immediately
    ResonatorState* h_state;
    BreathCommand*  h_cmd;
    LogEntry*       h_log;

    checkCuda(cudaMallocManaged(&h_state, sizeof(ResonatorState)), "cudaMallocManaged(state)");
    checkCuda(cudaMallocManaged(&h_cmd,   sizeof(BreathCommand)),  "cudaMallocManaged(cmd)");
    checkCuda(cudaMallocManaged(&h_log,   LOG_CAPACITY * sizeof(LogEntry)), "cudaMallocManaged(log)");

    // Init
    new (&h_state->write_idx) std::atomic<uint64_t>(0);
    new (&h_state->breaths)   std::atomic<uint64_t>(0);
    new (&h_state->dropped)   std::atomic<uint64_t>(0);
    new (&h_state->ns_period) std::atomic<uint64_t>(DEFAULT_SLEEP_NS);
    h_state->capacity  = LOG_CAPACITY;
    h_state->host_nonce = (uint64_t)std::chrono::high_resolution_clock::now().time_since_epoch().count();

    new (&h_cmd->opcode) std::atomic<uint32_t>(CMD_NONE);
    new (&h_cmd->param)  std::atomic<uint64_t>(0);
    new (&h_cmd->marker) std::atomic<uint64_t>(0);

    memset(h_log, 0, LOG_CAPACITY * sizeof(LogEntry));

    // Bind device globals
    checkCuda(cudaMemcpyToSymbol(g_state, &h_state, sizeof(h_state)), "MemcpyToSymbol g_state");
    checkCuda(cudaMemcpyToSymbol(g_cmd,   &h_cmd,   sizeof(h_cmd)),   "MemcpyToSymbol g_cmd");
    checkCuda(cudaMemcpyToSymbol(g_log,   &h_log,   sizeof(h_log)),   "MemcpyToSymbol g_log");

    // Launch persistent kernel
    breath_kernel<<<BLOCKS, TPB>>>();
    checkCuda(cudaGetLastError(), "kernel launch");

    printf("pmll_breath_resonator: running. Press ENTER to stop, 'm' + ENTER to mark, 's <ms>' to set period.\n");

    // Host-side printer loop
    uint64_t last_read = 0;
    auto last_print = std::chrono::steady_clock::now();

    // simple stdin watcher thread
    std::atomic<bool> stop_requested{false};
    std::thread input_thr([&](){
        std::string line;
        while (std::getline(std::cin, line)) {
            if (line.empty()) { stop_requested.store(true); break; }
            if (line == "m") {
                h_cmd->marker.store(h_state->host_nonce ^ (uint64_t)std::rand(), std::memory_order_relaxed);
                h_cmd->opcode.store(CMD_MARK, std::memory_order_release);
            } else if (line.size() && line[0] == 's') {
                // format: s 5   => 5 ms
                uint64_t ms = 0;
                if (sscanf(line.c_str(), "s %llu", (unsigned long long*)&ms) == 1) {
                    uint64_t ns = ms * 1'000'000ull;
                    h_cmd->param.store(ns, std::memory_order_relaxed);
                    h_cmd->opcode.store(CMD_SET_HZ, std::memory_order_release);
                    printf("[host] set period to %llu ns (%llums)\n",
                           (unsigned long long)ns, (unsigned long long)ms);
                }
            }
        }
    });

    while (!g_interrupted.load() && !stop_requested.load()) {
        uint64_t w = h_state->write_idx.load(std::memory_order_relaxed);
        while (last_read < w) {
            const LogEntry& e = h_log[last_read % h_state->capacity];
            printf("#%llu clk=%llu ent=0x%016llx digest=%08x%08x%08x%08x host_nonce=%016llx mark=%u\n",
                   (unsigned long long)e.seq,
                   (unsigned long long)e.clk,
                   (unsigned long long)e.entropy_mix,
                   e.digest[0], e.digest[1], e.digest[2], e.digest[3],
                   (unsigned long long)e.host_nonce,
                   e.marker_seen);
            last_read++;
        }

        // throttle host prints
        auto now = std::chrono::steady_clock::now();
        if (now - last_print > std::chrono::milliseconds(50)) {
            last_print = now;
        }
        std::this_thread::sleep_for(std::chrono::milliseconds(10));
    }

    // Request stop
    h_cmd->opcode.store(CMD_STOP, std::memory_order_release);

    // Wait for kernel to exit
    checkCuda(cudaDeviceSynchronize(), "cudaDeviceSynchronize");

    input_thr.join();

    // Stats
    printf("\nStopped. breaths=%llu dropped=%llu last_idx=%llu\n",
           (unsigned long long)h_state->breaths.load(),
           (unsigned long long)h_state->dropped.load(),
           (unsigned long long)h_state->write_idx.load());

    cudaFree(h_log);
    cudaFree(h_cmd);
    cudaFree(h_state);
    return 0;
}

# Create the integration files for wiring the breath resonator into a GPU integrity pass.
import textwrap, json, os, pathlib, sys

base = "/mnt/data/ppm_gpu_integrity"
os.makedirs(base, exist_ok=True)

files = {}

files["breath_gpu.h"] = r"""
// breath_gpu.h
// Shared library interface for the PMLL Breath GPU integrity engine.
// Build a shared library and load from Python via ctypes.
//
// License: MIT (2025) — provided as a scaffold.
//
// The engine runs a persistent CUDA kernel that:
// 1) Maintains a rhythmic "breath" loop for liveness.
// 2) Processes a host→device work queue of hashing jobs (SHA-256).
// 3) Emits receipts (digests + sequence numbers) that can be fetched from host.
//
// Notes:
// - Uses CUDA Unified Memory to keep the sample concise.
// - Production systems should allocate pinned host buffers and use streams.

#pragma once
#include <stdint.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// Error codes
enum {
    BREATH_OK            = 0,
    BREATH_ERR_CUDA      = -1,
    BREATH_ERR_ARGS      = -2,
    BREATH_ERR_NOSPACE   = -3,
    BREATH_ERR_NOTFOUND  = -4,
    BREATH_ERR_INTERNAL  = -5
};

// Initialize and start the engine.
// max_data_bytes: size of the device staging buffer for payloads.
// queue_len: number of concurrent work items allowed.
int breath_gpu_start(uint64_t max_data_bytes, int queue_len);

// Enqueue a hashing job.
// Returns BREATH_OK on success and assigns *out_id with job id.
int breath_gpu_enqueue(const void* data, uint64_t len, uint64_t tag, uint64_t* out_id);

// Poll a job. If done, writes digest[8], seq, and sets *out_done=1.
// Otherwise *out_done=0.
int breath_gpu_poll(uint64_t id, uint32_t digest[8], uint64_t* seq, int* out_done);

// Blocking wait for completion. Returns BREATH_OK when finished.
int breath_gpu_wait(uint64_t id, uint32_t digest[8], uint64_t* seq);

// Stop the engine and free resources.
int breath_gpu_stop(void);

// Utility: return a monotonic total breaths emitted by the kernel.
uint64_t breath_gpu_breaths(void);

// Utility: return dropped/overwritten log counter.
uint64_t breath_gpu_dropped(void);

#ifdef __cplusplus
} // extern "C"
#endif
"""

files["breath_gpu.cu"] = r"""
// breath_gpu.cu
// Implementation of a persistent CUDA "breath" kernel with a hashing work queue.
// See breath_gpu.h for API. This is a compact educational scaffold.

#include <cuda_runtime.h>
#include <cstdio>
#include <cstdint>
#include <cstring>
#include <atomic>
#include <new>
#include "breath_gpu.h"

// Tunables
static constexpr int   TPB   = 256;
static constexpr int   BLOCKS= 1;

// Commands for work items
enum : uint32_t {
    W_EMPTY = 0,
    W_READY = 1,
    W_DONE  = 2,
    W_BAD   = 3
};

struct WorkItem {
    std::atomic<uint32_t> state; // W_*
    uint64_t id;
    uint64_t tag;
    uint64_t off;    // byte offset in staging
    uint64_t len;    // bytes
    uint32_t digest[8];
    uint64_t seq;    // breath sequence when produced
};

struct EngineState {
    // Log / breath counters
    std::atomic<uint64_t> breaths;
    std::atomic<uint64_t> dropped;

    // Period (not used heavily in kernel to avoid watchdog)
    std::atomic<uint64_t> ns_period;

    // Queue
    std::atomic<uint64_t> write_idx;
    uint64_t              q_len;

    // staging buffer
    uint8_t*  staging;
    uint64_t  staging_bytes;
};

// Device globals
__device__ EngineState* d_estate = nullptr;
__device__ WorkItem*    d_queue  = nullptr;

// ------------- SHA-256 (device) -------------
__device__ __forceinline__ uint32_t rotr(uint32_t x, uint32_t n) {
    return (x >> n) | (x << (32 - n));
}
__device__ void sha256_transform(uint32_t s[8], const uint8_t block[64]) {
    const uint32_t K[64] = {
        0x428a2f98u,0x71374491u,0xb5c0fbcfu,0xe9b5dba5u,0x3956c25bu,0x59f111f1u,0x923f82a4u,0xab1c5ed5u,
        0xd807aa98u,0x12835b01u,0x243185beu,0x550c7dc3u,0x72be5d74u,0x80deb1feu,0x9bdc06a7u,0xc19bf174u,
        0xe49b69c1u,0xefbe4786u,0x0fc19dc6u,0x240ca1ccu,0x2de92c6fu,0x4a7484aau,0x5cb0a9dcu,0x76f988dau,
        0x983e5152u,0xa831c66du,0xb00327c8u,0xbf597fc7u,0xc6e00bf3u,0xd5a79147u,0x06ca6351u,0x14292967u,
        0x27b70a85u,0x2e1b2138u,0x4d2c6dfcu,0x53380d13u,0x650a7354u,0x766a0abbu,0x81c2c92eu,0x92722c85u,
        0xa2bfe8a1u,0xa81a664bu,0xc24b8b70u,0xc76c51a3u,0xd192e819u,0xd6990624u,0xf40e3585u,0x106aa070u,
        0x19a4c116u,0x1e376c08u,0x2748774cu,0x34b0bcb5u,0x391c0cb3u,0x4ed8aa4au,0x5b9cca4fu,0x682e6ff3u,
        0x748f82eeu,0x78a5636fu,0x84c87814u,0x8cc70208u,0x90befffau,0xa4506cebu,0xbef9a3f7u,0xc67178f2u
    };
    uint32_t w[64];
#pragma unroll
    for (int i=0;i<16;++i){
        w[i] = (uint32_t)block[i*4+0]<<24 | (uint32_t)block[i*4+1]<<16 |
               (uint32_t)block[i*4+2]<<8  | (uint32_t)block[i*4+3];
    }
#pragma unroll
    for (int i=16;i<64;++i){
        uint32_t s0 = rotr(w[i-15],7) ^ rotr(w[i-15],18) ^ (w[i-15]>>3);
        uint32_t s1 = rotr(w[i-2],17) ^ rotr(w[i-2],19) ^ (w[i-2]>>10);
        w[i] = w[i-16] + s0 + w[i-7] + s1;
    }
    uint32_t a=0x6a09e667u,b=0xbb67ae85u,c=0x3c6ef372u,d=0xa54ff53au;
    uint32_t e=0x510e527fu,f=0x9b05688cu,g=0x1f83d9abu,h=0x5be0cd19u;
#pragma unroll
    for (int i=0;i<64;++i){
        uint32_t S1 = rotr(e,6)^rotr(e,11)^rotr(e,25);
        uint32_t ch = (e&f) ^ ((~e)&g);
        uint32_t t1 = h + S1 + ch + K[i] + w[i];
        uint32_t S0 = rotr(a,2)^rotr(a,13)^rotr(a,22);
        uint32_t maj= (a&b) ^ (a&c) ^ (b&c);
        uint32_t t2 = S0 + maj;
        h=g; g=f; f=e; e=d+t1; d=c; c=b; b=a; a=t1+t2;
    }
    s[0]=a; s[1]=b; s[2]=c; s[3]=d; s[4]=e; s[5]=f; s[6]=g; s[7]=h;
}

__device__ void sha256_bytes(const uint8_t* data, uint64_t len, uint32_t out[8]){
    uint32_t H[8]={0x6a09e667u,0xbb67ae85u,0x3c6ef372u,0xa54ff53au,
                   0x510e527fu,0x9b05688cu,0x1f83d9abu,0x5be0cd19u};
    uint8_t block[64];
    uint64_t full = len & ~((uint64_t)63);
    for (uint64_t i=0;i<full;i+=64) sha256_transform(H, data+i);
    uint64_t rem = len-full;
    memset(block,0,64);
    if (rem) memcpy(block, data+full, rem);
    block[rem] = 0x80;
    uint64_t bitlen = len*8ull;
    if (rem >= 56){
        sha256_transform(H, block);
        memset(block,0,64);
    }
    for (int i=0;i<8;++i) block[56+i]=(uint8_t)(bitlen>>(56-8*i));
    sha256_transform(H, block);
#pragma unroll
    for (int i=0;i<8;++i) out[i]=H[i];
}

// ------------- Kernel -------------
__global__ void breath_worker() {
    const uint32_t tid = threadIdx.x;
    auto* es = d_estate;
    auto* q  = d_queue;

    while (true) {
        // Breath tick (collective)
        uint64_t clk = clock64();
        __syncthreads();

        // Find a ready work item (thread 0 scans linearly; fine for demo)
        int picked = -1;
        if (tid==0){
            for (uint64_t i=0;i<es->q_len;++i){
                uint32_t st = q[i].state.load(std::memory_order_relaxed);
                if (st == W_READY){
                    picked = (int)i;
                    break;
                }
            }
        }
        __shared__ int s_idx;
        if (tid==0) s_idx = picked;
        __syncthreads();
        if (s_idx >= 0){
            // Hash by thread 0 for simplicity (extend to parallel later)
            if (tid==0){
                WorkItem &w = q[s_idx];
                const uint8_t* ptr = es->staging + w.off;
                uint32_t dig[8];
                sha256_bytes(ptr, w.len, dig);
#pragma unroll
                for (int i=0;i<8;++i) w.digest[i] = dig[i];
                uint64_t seq = es->breaths.load(std::memory_order_relaxed);
                w.seq = seq;
                w.state.store(W_DONE, std::memory_order_release);
            }
        }

        // Increment breath counter lightly
        if (tid==0) {
            uint64_t b = es->breaths.load(std::memory_order_relaxed);
            es->breaths.store(b+1, std::memory_order_relaxed);
        }

        // small spin to avoid watchdog overrun
        uint64_t goal = clock64() + 50000;
        while (clock64() < goal) { }
        __syncthreads();
    }
}

// ------------- Host state -------------
static EngineState* h_es = nullptr;
static WorkItem*    h_q  = nullptr;
static cudaStream_t stream0 = nullptr;

// helpers
static int ck(cudaError_t e, const char* msg){
    if (e != cudaSuccess){
        fprintf(stderr, "CUDA error at %s: %s\n", msg, cudaGetErrorString(e));
        return BREATH_ERR_CUDA;
    }
    return BREATH_OK;
}

extern "C" int breath_gpu_start(uint64_t max_data_bytes, int queue_len){
    if (queue_len <= 0 || max_data_bytes < 64) return BREATH_ERR_ARGS;

    if (int rc = ck(cudaMallocManaged(&h_es, sizeof(EngineState)), "alloc estate")) return rc;
    if (int rc = ck(cudaMallocManaged(&h_q,  queue_len * sizeof(WorkItem)), "alloc queue")) return rc;

    // staging buffer
    uint8_t* staging=nullptr;
    if (int rc = ck(cudaMallocManaged(&staging, max_data_bytes), "alloc staging")) return rc;

    // placement-new atomics
    new (&h_es->breaths) std::atomic<uint64_t>(0);
    new (&h_es->dropped) std::atomic<uint64_t>(0);
    new (&h_es->ns_period) std::atomic<uint64_t>(2'000'000ull);
    new (&h_es->write_idx) std::atomic<uint64_t>(0);
    h_es->q_len = (uint64_t)queue_len;
    h_es->staging = staging;
    h_es->staging_bytes = max_data_bytes;

    for (int i=0;i<queue_len;++i){
        new (&h_q[i].state) std::atomic<uint32_t>(W_EMPTY);
        h_q[i].id = 0; h_q[i].tag = 0; h_q[i].off = 0; h_q[i].len = 0; h_q[i].seq=0;
        memset(h_q[i].digest, 0, sizeof(h_q[i].digest));
    }

    if (int rc = ck(cudaMemcpyToSymbol(d_estate, &h_es, sizeof(h_es)), "sym estate")) return rc;
    if (int rc = ck(cudaMemcpyToSymbol(d_queue,  &h_q,  sizeof(h_q)),  "sym queue")) return rc;

    if (int rc = ck(cudaStreamCreate(&stream0), "stream create")) return rc;

    breath_worker<<<BLOCKS, TPB, 0, stream0>>>();
    if (int rc = ck(cudaGetLastError(), "kernel launch")) return rc;

    return BREATH_OK;
}

extern "C" int breath_gpu_enqueue(const void* data, uint64_t len, uint64_t tag, uint64_t* out_id){
    if (!h_es || !h_q) return BREATH_ERR_INTERNAL;
    if (!data || len==0 || len > h_es->staging_bytes) return BREATH_ERR_ARGS;

    // find free slot
    int slot = -1;
    for (uint64_t i=0;i<h_es->q_len;++i){
        uint32_t st = h_q[i].state.load(std::memory_order_relaxed);
        if (st == W_EMPTY){
            slot = (int)i; break;
        }
    }
    if (slot < 0) return BREATH_ERR_NOSPACE;

    // copy into staging (synchronously for simplicity)
    memcpy(h_es->staging, data, (size_t)len);

    uint64_t id = h_es->write_idx.load(std::memory_order_relaxed) + 1;
    h_es->write_idx.store(id, std::memory_order_relaxed);

    WorkItem &w = h_q[slot];
    w.id  = id;
    w.tag = tag;
    w.off = 0;
    w.len = len;
    w.state.store(W_READY, std::memory_order_release);
    if (out_id) *out_id = id;
    return BREATH_OK;
}

extern "C" int breath_gpu_poll(uint64_t id, uint32_t digest[8], uint64_t* seq, int* out_done){
    if (!h_es || !h_q) return BREATH_ERR_INTERNAL;
    if (!out_done) return BREATH_ERR_ARGS;
    *out_done = 0;

    for (uint64_t i=0;i<h_es->q_len;++i){
        if (h_q[i].id == id){
            uint32_t st = h_q[i].state.load(std::memory_order_acquire);
            if (st == W_DONE){
                if (digest) memcpy(digest, h_q[i].digest, sizeof(h_q[i].digest));
                if (seq) *seq = h_q[i].seq;
                h_q[i].state.store(W_EMPTY, std::memory_order_release);
                *out_done = 1;
            }
            return BREATH_OK;
        }
    }
    return BREATH_ERR_NOTFOUND;
}

extern "C" int breath_gpu_wait(uint64_t id, uint32_t digest[8], uint64_t* seq){
    if (!h_es || !h_q) return BREATH_ERR_INTERNAL;
    while (true){
        int done=0;
        int rc = breath_gpu_poll(id, digest, seq, &done);
        if (rc != BREATH_OK) return rc;
        if (done) return BREATH_OK;
        // light sync
        cudaDeviceSynchronize(); // allow UM to propagate
    }
}

extern "C" int breath_gpu_stop(void){
    if (!h_es) return BREATH_OK;
    cudaDeviceReset(); // stops kernel

    // free
    if (h_es->staging) cudaFree(h_es->staging);
    cudaFree(h_q);
    cudaFree(h_es);
    h_es = nullptr; h_q = nullptr;
    return BREATH_OK;
}

extern "C" uint64_t breath_gpu_breaths(void){
    if (!h_es) return 0;
    return h_es->breaths.load(std::memory_order_relaxed);
}
extern "C" uint64_t breath_gpu_dropped(void){
    if (!h_es) return 0;
    return h_es->dropped.load(std::memory_order_relaxed);
}
"""

files["gpu_integrity.py"] = r"""
"""
# We'll fill gpu_integrity.py next
files["gpu_integrity.py"] = r'''
"""
gpu_integrity.py — Python wrapper for the Breath GPU integrity engine.

Usage:
    from gpu_integrity import GPUIntegrity

    eng = GPUIntegrity()
    eng.start()
    receipt = eng.hash_bytes(b"hello world", tag=0x1234)
    print(receipt)
    eng.stop()
"""

import ctypes as C
import os, pathlib, json
from dataclasses import dataclass

# Expect the shared library name
_DEFAULT_NAMES = ["libbreath_gpu.so", "breath_gpu.dll", "libbreath_gpu.dylib"]

@dataclass
class Receipt:
    id: int
    seq: int
    digest: list  # 8 uint32 words
    tag: int

class GPUIntegrity:
    def __init__(self, lib_path=None, max_data_bytes=16*1024*1024, queue_len=64):
        self.max_data_bytes = int(max_data_bytes)
        self.queue_len = int(queue_len)
        self.lib = None

        if lib_path is None:
            # try current directory
            here = pathlib.Path(__file__).parent
            for name in _DEFAULT_NAMES:
                cand = here / name
                if cand.exists():
                    lib_path = str(cand)
                    break
        if lib_path is None:
            raise FileNotFoundError("Shared library not found. Provide lib_path.")

        self.lib = C.CDLL(lib_path)

        # declare signatures
        self.lib.breath_gpu_start.argtypes = [C.c_uint64, C.c_int]
        self.lib.breath_gpu_start.restype  = C.c_int

        self.lib.breath_gpu_enqueue.argtypes = [C.c_void_p, C.c_uint64, C.c_uint64, C.POINTER(C.c_uint64)]
        self.lib.breath_gpu_enqueue.restype  = C.c_int

        self.lib.breath_gpu_poll.argtypes = [C.c_uint64, C.POINTER(C.c_uint32), C.POINTER(C.c_uint64), C.POINTER(C.c_int)]
        self.lib.breath_gpu_poll.restype  = C.c_int

        self.lib.breath_gpu_wait.argtypes = [C.c_uint64, C.POINTER(C.c_uint32), C.POINTER(C.c_uint64)]
        self.lib.breath_gpu_wait.restype  = C.c_int

        self.lib.breath_gpu_stop.argtypes = []
        self.lib.breath_gpu_stop.restype  = C.c_int

    def start(self):
        rc = self.lib.breath_gpu_start(self.max_data_bytes, self.queue_len)
        if rc != 0:
            raise RuntimeError(f"breath_gpu_start failed: {rc}")

    def stop(self):
        self.lib.breath_gpu_stop()

    def hash_bytes(self, data: bytes, tag: int = 0) -> Receipt:
        buf = C.create_string_buffer(data)
        out_id = C.c_uint64(0)
        rc = self.lib.breath_gpu_enqueue(buf, len(data), C.c_uint64(tag), C.byref(out_id))
        if rc != 0:
            raise RuntimeError(f"enqueue failed: {rc}")
        digest = (C.c_uint32 * 8)()
        seq = C.c_uint64(0)
        rc = self.lib.breath_gpu_wait(out_id.value, digest, C.byref(seq))
        if rc != 0:
            raise RuntimeError(f"wait failed: {rc}")
        return Receipt(
            id=int(out_id.value),
            seq=int(seq.value),
            digest=[int(digest[i]) for i in range(8)],
            tag=int(tag),
        )

    @staticmethod
    def digest_hex(words):
        return "".join(f"{w:08x}" for w in words)

    def receipt_json(self, receipt: Receipt, path: str = None) -> str:
        obj = {
            "id": receipt.id,
            "seq": receipt.seq,
            "digest_words": receipt.digest,
            "digest_hex": self.digest_hex(receipt.digest),
            "tag": receipt.tag,
        }
        s = json.dumps(obj, indent=2)
        if path:
            with open(path, "w") as f:
                f.write(s)
        return s
'''

files["BUILD.md"] = r"""
# Breath GPU Integrity — Build & Wire-in

## Build the shared library

```bash
cd ppm_gpu_integrity
nvcc -O3 -std=c++17 -Xcompiler -fPIC -shared breath_gpu.cu -o libbreath_gpu.so
```

> macOS: replace `-o libbreath_gpu.so` with `-o libbreath_gpu.dylib`  
> Windows (MSYS/WSL): build `breath_gpu.dll` with appropriate flags.

## Test from Python

```bash
python3 - <<'PY'
from gpu_integrity import GPUIntegrity
eng = GPUIntegrity(lib_path="./libbreath_gpu.so")
eng.start()
r = eng.hash_bytes(b"hello world", tag=0x1234)
print("SEQ", r.seq, "DIGEST", GPUIntegrity.digest_hex(r.digest))
eng.stop()
PY
```

Expected output prints a sequence number and a SHA-256 digest.

## Wire into PPM resolver

In your `resolver.py` (or integrity step), add:

```python
from gpu_integrity import GPUIntegrity

gpu = None
try:
    gpu = GPUIntegrity(lib_path="path/to/libbreath_gpu.so", max_data_bytes=32*1024*1024, queue_len=128)
    gpu.start()
except Exception as e:
    gpu = None
    print("[ppm] GPU integrity disabled:", e)

def gpu_hash_bytes(data: bytes):
    if not gpu:
        import hashlib
        return hashlib.sha256(data).hexdigest(), None
    rec = gpu.hash_bytes(data, tag=0)
    return GPUIntegrity.digest_hex(rec.digest), {"seq": rec.seq, "id": rec.id}

# Example in artifact verification:
# content = open(wheel_path, "rb").read()
# digest_hex, receipt = gpu_hash_bytes(content)
# record receipt to JSON provenance.
```

## Provenance JSON example

```json
{
  "artifact": "some-1.2.3-py3-none-any.whl",
  "sha256": "e3b0c44298fc1c149afbf4c8996fb924...",
  "gpu_receipt": {
    "id": 7,
    "seq": 1042
  }
}
```

Optionally sign this JSON with Ed25519 and store alongside the wheel.
"""

# Write files
for name, content in files.items():
    with open(os.path.join(base, name), "w") as f:
        f.write(content)

list(files.keys()), base

# Create Ed25519-signing CLI that integrates the GPU integrity engine.
import os, json, textwrap, pathlib, sys

base = "/mnt/data/ppm_gpu_integrity"
os.makedirs(base, exist_ok=True)

ppm_cli = r'''
#!/usr/bin/env python3
"""
ppm_cli.py — signing + GPU integrity receipts for PPM artifacts.

Subcommands
  genkey                Generate an Ed25519 keypair.
  sign                  Hash file, optionally GPU-receipt, sign JSON.
  verify                Verify a receipt JSON against file and public key.
  hash                  Plain SHA-256 of a file.
  gpu-hash              Return GPU receipt only.

Ed25519 backend:
  - Prefers PyNaCl. If unavailable, tries 'cryptography'.
  - If neither found, exits with helpful instructions.
"""

import argparse, os, sys, json, hashlib, base64, binascii, time
from dataclasses import dataclass, asdict
from pathlib import Path

# ==== Ed25519 backend selection ====
def _load_ed25519():
    try:
        from nacl.signing import SigningKey, VerifyKey
        from nacl.exceptions import BadSignatureError
        return ("pynacl", SigningKey, VerifyKey, BadSignatureError)
    except Exception:
        pass
    try:
        # cryptography
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PrivateKey, Ed25519PublicKey
        )
        from cryptography.hazmat.primitives import serialization
        class SigningKey:
            def __init__(self, sk_bytes):
                self._sk = Ed25519PrivateKey.from_private_bytes(sk_bytes)
                self._vk = self._sk.public_key()
            @classmethod
            def generate(cls):
                sk = Ed25519PrivateKey.generate()
                sk_bytes = sk.private_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PrivateFormat.Raw,
                    encryption_algorithm=serialization.NoEncryption(),
                )
                return cls(sk_bytes)
            def sign(self, data: bytes)->bytes:
                return self._sk.sign(data)
            @property
            def verify_key(self):
                return VerifyKey(self._vk.public_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PublicFormat.Raw
                ))
            @property
            def _seed(self):
                # cryptography doesn't expose seed; return private bytes
                from cryptography.hazmat.primitives import serialization
                return self._sk.private_bytes(
                    encoding=serialization.Encoding.Raw,
                    format=serialization.PrivateFormat.Raw,
                    encryption_algorithm=serialization.NoEncryption(),
                )
        class VerifyKey:
            def __init__(self, vk_bytes):
                self._vk = Ed25519PublicKey.from_public_bytes(vk_bytes)
                self._bytes = vk_bytes
            def verify(self, sig: bytes, data: bytes):
                self._vk.verify(sig, data)
            @property
            def encode(self):
                return self._bytes
            def __bytes__(self):
                return self._bytes
        class BadSignatureError(Exception):
            pass
        return ("cryptography", SigningKey, VerifyKey, BadSignatureError)
    except Exception:
        pass
    return (None, None, None, None)

backend_name, SigningKey, VerifyKey, BadSignatureError = _load_ed25519()

# ==== GPU wrapper (optional) ====
def load_gpu(lib_path):
    from ctypes import CDLL, c_uint64, c_uint32, c_void_p, POINTER, c_int
    lib = CDLL(lib_path)
    lib.breath_gpu_start.argtypes = [c_uint64, c_int]
    lib.breath_gpu_start.restype  = c_int
    lib.breath_gpu_enqueue.argtypes = [c_void_p, c_uint64, c_uint64, POINTER(c_uint64)]
    lib.breath_gpu_enqueue.restype  = c_int
    lib.breath_gpu_wait.argtypes = [c_uint64, POINTER(c_uint32), POINTER(c_uint64)]
    lib.breath_gpu_wait.restype  = c_int
    lib.breath_gpu_stop.argtypes = []
    lib.breath_gpu_stop.restype  = c_int
    return lib

def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1<<20), b""):
            h.update(chunk)
    return h.digest()

@dataclass
class GPUReceipt:
    id: int
    seq: int
    digest_words: list
    digest_hex: str

@dataclass
class Receipt:
    artifact: str
    size: int
    sha256_hex: str
    created_utc: int
    gpu_receipt: GPUReceipt|None
    signer_pk: str
    signature_b64: str

def hex_of(words):
    return "".join(f"{w:08x}" for w in words)

def cmd_genkey(args):
    if backend_name is None:
        print("Ed25519 backend not found. Install one of:\n  pip install pynacl\n  pip install cryptography", file=sys.stderr)
        sys.exit(2)
    if args.seed:
        seed = binascii.unhexlify(args.seed)
        if len(seed) != 32:
            print("Seed must be 32-byte hex.", file=sys.stderr)
            sys.exit(2)
        sk = SigningKey(seed)
    else:
        sk = SigningKey.generate()
    # PyNaCl exposes .verify_key.encode(); cryptography wrapper returns bytes via property
    try:
        pk_bytes = bytes(sk.verify_key)
    except TypeError:
        pk_bytes = sk.verify_key.encode if hasattr(sk.verify_key, "encode") else bytes(sk.verify_key)
    try:
        seed_bytes = sk._seed
    except Exception:
        # not all backends expose; okay
        seed_bytes = None
    obj = {
        "backend": backend_name,
        "public_key_hex": pk_bytes.hex(),
        "seed_hex": seed_bytes.hex() if seed_bytes else None,
    }
    Path(args.out).write_text(json.dumps(obj, indent=2))
    print(f"wrote {args.out}")

def cmd_sign(args):
    if backend_name is None:
        print("Missing Ed25519 backend. Install pynacl or cryptography.", file=sys.stderr)
        sys.exit(2)
    key = json.loads(Path(args.sk).read_text())
    pk_hex = key["public_key_hex"]
    seed_hex = key.get("seed_hex")
    if not seed_hex:
        print("This key file does not include a seed/private key. Recreate with --seed or PyNaCl.", file=sys.stderr); sys.exit(2)
    sk = SigningKey(binascii.unhexlify(seed_hex))

    artifact = args.file
    sha = sha256_file(artifact)
    sha_hex = sha.hex()
    gpu_rec = None
    if args.gpu:
        lib = load_gpu(args.gpu)
        if lib.breath_gpu_start(32*1024*1024, 64) != 0:
            print("GPU start failed", file=sys.stderr); sys.exit(2)
        # read file into memory for this demo (could stream into staging incrementally)
        data = Path(artifact).read_bytes()
        from ctypes import c_uint64, c_uint32, c_int, create_string_buffer, byref, POINTER
        buf = create_string_buffer(data)
        out_id = c_uint64(0)
        rc = lib.breath_gpu_enqueue(buf, len(data), c_uint64(0), byref(out_id))
        if rc != 0:
            print("enqueue failed", file=sys.stderr); sys.exit(2)
        dig = (c_uint32*8)()
        seq = c_uint64(0)
        rc = lib.breath_gpu_wait(out_id.value, dig, byref(seq))
        if rc != 0:
            print("wait failed", file=sys.stderr); sys.exit(2)
        lib.breath_gpu_stop()
        words = [int(dig[i]) for i in range(8)]
        gpu_rec = GPUReceipt(
            id=int(out_id.value),
            seq=int(seq.value),
            digest_words=words,
            digest_hex=hex_of(words),
        )

    payload = {
        "artifact": os.path.basename(artifact),
        "size": os.path.getsize(artifact),
        "sha256_hex": sha_hex,
        "created_utc": int(time.time()),
        "gpu_receipt": asdict(gpu_rec) if gpu_rec else None,
        "signer_pk": pk_hex,
    }
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",",":")).encode()
    sig = sk.sign(payload_bytes)
    # PyNaCl returns signed message; cryptography returns signature only
    if backend_name == "pynacl":
        signature = sig.signature
    else:
        signature = sig
    receipt = dict(payload)
    receipt["signature_b64"] = base64.b64encode(signature).decode()

    out = args.out or (artifact + ".receipt.json")
    Path(out).write_text(json.dumps(receipt, indent=2))
    print(f"wrote {out}")
    return 0

def cmd_verify(args):
    receipt = json.loads(Path(args.receipt).read_text())
    pk_hex = args.pk or receipt.get("signer_pk")
    if not pk_hex:
        print("No public key provided.", file=sys.stderr); sys.exit(2)
    vk = VerifyKey(binascii.unhexlify(pk_hex))
    sig = base64.b64decode(receipt["signature_b64"])

    # Rebuild payload
    payload = {k: receipt[k] for k in ["artifact","size","sha256_hex","created_utc","gpu_receipt","signer_pk"]}
    payload_bytes = json.dumps(payload, sort_keys=True, separators=(",",":")).encode()

    # verify signature
    try:
        vk.verify(sig, payload_bytes)
    except Exception as e:
        # PyNaCl expects verify(message) includes signed msg; our adapter calls vk.verify(sig,data)
        try:
            # PyNaCl path
            from nacl.signing import VerifyKey as VK2
            if isinstance(vk, VK2):
                vk.verify(payload_bytes, sig)  # will raise if bad
            else:
                raise
        except Exception as e2:
            print("BAD SIGNATURE:", e2, file=sys.stderr); sys.exit(3)

    # check file metrics if provided
    if args.file:
        if os.path.getsize(args.file) != receipt["size"]:
            print("Size mismatch.", file=sys.stderr); sys.exit(4)
        sha_hex = sha256_file(args.file).hex()
        if sha_hex != receipt["sha256_hex"]:
            print("SHA-256 mismatch.", file=sys.stderr); sys.exit(5)

    print("OK")
    return 0

def cmd_hash(args):
    print(sha256_file(args.file).hex())

def cmd_gpu_hash(args):
    lib = load_gpu(args.gpu)
    if lib.breath_gpu_start(32*1024*1024, 64) != 0:
        print("GPU start failed", file=sys.stderr); sys.exit(2)
    data = Path(args.file).read_bytes()
    from ctypes import c_uint64, c_uint32, create_string_buffer, byref
    buf = create_string_buffer(data)
    out_id = c_uint64(0)
    rc = lib.breath_gpu_enqueue(buf, len(data), c_uint64(0), byref(out_id))
    if rc != 0:
        print("enqueue failed", file=sys.stderr); sys.exit(2)
    dig = (c_uint32*8)()
    seq = c_uint64(0)
    rc = lib.breath_gpu_wait(out_id.value, dig, byref(seq))
    if rc != 0:
        print("wait failed", file=sys.stderr); sys.exit(2)
    lib.breath_gpu_stop()
    words = [int(dig[i]) for i in range(8)]
    print(json.dumps({
        "id": int(out_id.value),
        "seq": int(seq.value),
        "digest_words": words,
        "digest_hex": hex_of(words),
    }, indent=2))

def main():
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)

    p = sp.add_parser("genkey")
    p.add_argument("--out", required=True)
    p.add_argument("--seed", help="32-byte hex seed (optional)")
    p.set_defaults(func=cmd_genkey)

    p = sp.add_parser("sign")
    p.add_argument("--sk", required=True, help="key file from genkey")
    p.add_argument("--file", required=True)
    p.add_argument("--gpu", help="path to libbreath_gpu.so (optional)")
    p.add_argument("--out")
    p.set_defaults(func=cmd_sign)

    p = sp.add_parser("verify")
    p.add_argument("--receipt", required=True)
    p.add_argument("--file", help="artifact path to compare")
    p.add_argument("--pk", help="public key hex (overrides receipt)")
    p.set_defaults(func=cmd_verify)

    p = sp.add_parser("hash")
    p.add_argument("--file", required=True)
    p.set_defaults(func=cmd_hash)

    p = sp.add_parser("gpu-hash")
    p.add_argument("--file", required=True)
    p.add_argument("--gpu", required=True)
    p.set_defaults(func=cmd_gpu_hash)

    args = ap.parse_args()
    sys.exit(args.func(args))

if __name__ == "__main__":
    main()
'''

with open(os.path.join(base, "ppm_cli.py"), "w") as f:
    f.write(ppm_cli)

os.chmod(os.path.join(base, "ppm_cli.py"), 0o755)

print("Created CLI at", os.path.join(base, "ppm_cli.py"))
