// matrix.cu
#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <vector>
#include <string>
#include <fstream>
#include <sstream>
#include <iostream>

#include "importresolver.h"
#include <cuda_runtime.h>

#define CUDA_OK(call) do { \
  cudaError_t _e = (call); \
  if (_e != cudaSuccess) { \
    fprintf(stderr, "[cuda] %s failed: %s\n", #call, cudaGetErrorString(_e)); \
    return -1; \
  } \
} while(0)

static const uint32_t K256[64] = {
  0x428a2f98U,0x71374491U,0xb5c0fbcfU,0xe9b5dba5U,0x3956c25bU,0x59f111f1U,0x923f82a4U,0xab1c5ed5U,
  0xd807aa98U,0x12835b01U,0x243185beU,0x550c7dc3U,0x72be5d74U,0x80deb1feU,0x9bdc06a7U,0xc19bf174U,
  0xe49b69c1U,0xefbe4786U,0x0fc19dc6U,0x240ca1ccU,0x2de92c6fU,0x4a7484aaU,0x5cb0a9dcU,0x76f988daU,
  0x983e5152U,0xa831c66dU,0xb00327c8U,0xbf597fc7U,0xc6e00bf3U,0xd5a79147U,0x06ca6351U,0x14292967U,
  0x27b70a85U,0x2e1b2138U,0x4d2c6dfcU,0x53380d13U,0x650a7354U,0x766a0abbU,0x81c2c92eU,0x92722c85U,
  0xa2bfe8a1U,0xa81a664bU,0xc24b8b70U,0xc76c51a3U,0xd192e819U,0xd6990624U,0xf40e3585U,0x106aa070U,
  0x19a4c116U,0x1e376c08U,0x2748774cU,0x34b0bcb5U,0x391c0cb3U,0x4ed8aa4aU,0x5b9cca4fU,0x682e6ff3U,
  0x748f82eeU,0x78a5636fU,0x84c87814U,0x8cc70208U,0x90befffaU,0xa4506cebU,0xbef9a3f7U,0xc67178f2U
};

__device__ __forceinline__ uint32_t rotr(uint32_t x, uint32_t n){
  return (x >> n) | (x << (32 - n));
}

__device__ void sha256_blocks(const uint8_t* data, size_t nblocks, uint32_t* H){
  uint32_t a,b,c,d,e,f,g,h,w[64];
  for (size_t block = 0; block < nblocks; ++block){
    #pragma unroll
    for (int t=0;t<16;++t){
      int i = block*64 + t*4;
      w[t] = (uint32_t)data[i]<<24 | (uint32_t)data[i+1]<<16 | (uint32_t)data[i+2]<<8 | (uint32_t)data[i+3];
    }
    #pragma unroll
    for (int t=16;t<64;++t){
      uint32_t s0 = rotr(w[t-15],7) ^ rotr(w[t-15],18) ^ (w[t-15]>>3);
      uint32_t s1 = rotr(w[t-2],17) ^ rotr(w[t-2],19) ^ (w[t-2]>>10);
      w[t] = w[t-16] + s0 + w[t-7] + s1;
    }
    a=H[0]; b=H[1]; c=H[2]; d=H[3]; e=H[4]; f=H[5]; g=H[6]; h=H[7];
    #pragma unroll
    for (int t=0;t<64;++t){
      uint32_t S1 = rotr(e,6) ^ rotr(e,11) ^ rotr(e,25);
      uint32_t ch = (e & f) ^ ((~e) & g);
      uint32_t temp1 = h + S1 + ch + K256[t] + w[t];
      uint32_t S0 = rotr(a,2) ^ rotr(a,13) ^ rotr(a,22);
      uint32_t maj = (a & b) ^ (a & c) ^ (b & c);
      uint32_t temp2 = S0 + maj;
      h=g; g=f; f=e; e=d + temp1;
      d=c; c=b; b=a; a=temp1 + temp2;
    }
    H[0]+=a; H[1]+=b; H[2]+=c; H[3]+=d; H[4]+=e; H[5]+=f; H[6]+=g; H[7]+=h;
  }
}

__global__ void sha256_kernel(const uint8_t **d_ptrs,
                              const size_t  *d_sizes,
                              uint8_t       *d_digests,
                              int nfiles)
{
  int idx = blockIdx.x;
  if (idx >= nfiles) return;

  const uint8_t *data = d_ptrs[idx];
  size_t size = d_sizes[idx];

  // Initial hash values
  uint32_t H[8] = {
    0x6a09e667U,0xbb67ae85U,0x3c6ef372U,0xa54ff53aU,
    0x510e527fU,0x9b05688cU,0x1f83d9abU,0x5be0cd19U
  };

  // Process full blocks
  size_t full = size / 64;
  sha256_blocks(data, full, H);

  // Tail + padding in shared/local buffer (<= 2 blocks)
  uint8_t tail[128];
  size_t tail_len = size - full*64;
  for (size_t i=0;i<tail_len;++i) tail[i] = data[full*64+i];

  // append 0x80
  tail[tail_len++] = 0x80;
  // pad with zeros until last 8 bytes remain for length
  size_t pad_len = ((tail_len <= 56) ? (56 - tail_len) : (120 - tail_len));
  for (size_t i=0;i<pad_len;++i) tail[tail_len++] = 0x00;

  // message length in bits (big-endian)
  uint64_t bitlen = (uint64_t)size * 8ULL;
  for (int i=7;i>=0;--i){
    tail[tail_len++] = (uint8_t)((bitlen >> (i*8)) & 0xff);
  }

  // process the remaining 1 or 2 blocks
  sha256_blocks(tail, tail_len/64, H);

  // write digest
  uint8_t *out = d_digests + idx*32;
  #pragma unroll
  for (int i=0;i<8;++i){
    out[i*4+0] = (uint8_t)((H[i] >> 24) & 0xff);
    out[i*4+1] = (uint8_t)((H[i] >> 16) & 0xff);
    out[i*4+2] = (uint8_t)((H[i] >> 8) & 0xff);
    out[i*4+3] = (uint8_t)( H[i]        & 0xff);
  }
}

/* -------------- tiny helpers -------------- */

static std::string to_hex(const uint8_t *bytes, size_t n){
  static const char *h = "0123456789abcdef";
  std::string s; s.resize(n*2);
  for (size_t i=0;i<n;++i){
    s[2*i]   = h[(bytes[i]>>4)&0xf];
    s[2*i+1] = h[bytes[i]&0xf];
  }
  return s;
}

struct FileItem {
  std::string filename;   // e.g., torch-2.7.0...whl
  std::string expected;   // sha256 hex
  std::vector<uint8_t> bytes; // file content
};

static int load_inputs(const char *root, const char *inputs_path, std::vector<FileItem> &items){
  std::ifstream in(inputs_path);
  if (!in) { fprintf(stderr,"[matrix] open %s failed\n", inputs_path); return -1; }
  std::string line;
  while (std::getline(in, line)){
    if (line.empty()) continue;
    std::string file, sha;
    size_t tab = line.find('\t');
    if (tab == std::string::npos) continue;
    file = line.substr(0, tab);
    sha = line.substr(tab+1);
    FileItem it;
    it.filename = file;
    it.expected = sha;
    // read cache/<file>
    std::string full = std::string(root) + "/.ppm/cache/" + file;
    std::ifstream f(full, std::ios::binary);
    if (!f) { fprintf(stderr,"[matrix] missing cache file: %s\n", full.c_str()); return -1; }
    f.seekg(0, std::ios::end);
    size_t sz = (size_t)f.tellg();
    f.seekg(0);
    it.bytes.resize(sz);
    if (sz) f.read((char*)it.bytes.data(), sz);
    items.emplace_back(std::move(it));
  }
  return 0;
}

static int write_report(const char *report_path,
                        const std::vector<FileItem> &items,
                        const std::vector<std::string> &got_hex,
                        int mismatches)
{
  std::ofstream out(report_path);
  if (!out) { fprintf(stderr,"[matrix] write %s failed\n", report_path); return -1; }
  out << "{\n  \"mismatches\": " << mismatches << ",\n  \"results\": [\n";
  for (size_t i=0;i<items.size();++i){
    out << "    {\"filename\": \"" << items[i].filename << "\", "
        << "\"expected\": \"" << items[i].expected << "\", "
        << "\"actual\": \"" << got_hex[i] << "\"}";
    out << (i+1<items.size() ? ",\n" : "\n");
  }
  out << "  ]\n}\n";
  return 0;
}

/* -------------- public API -------------- */

int ir_matrix_verify_cuda(const char *root,
                          const char *matrix_inputs_path,
                          const char *report_path,
                          int *out_mismatch_count)
{
  if (out_mismatch_count) *out_mismatch_count = -1;

  std::vector<FileItem> items;
  if (load_inputs(root, matrix_inputs_path, items) != 0) return -1;
  int n = (int)items.size();
  if (n == 0){
    std::ofstream out(report_path);
    if (out) out << "{ \"mismatches\": 0, \"results\": [] }\n";
    if (out_mismatch_count) *out_mismatch_count = 0;
    return 0;
  }

  // host arrays of device pointers and sizes
  std::vector<const uint8_t*> h_ptrs(n,nullptr);
  std::vector<size_t>         h_sizes(n,0);

  // allocate device buffers per file
  std::vector<uint8_t*> d_filebufs(n,nullptr);
  for (int i=0;i<n;++i){
    if (!items[i].bytes.empty()){
      CUDA_OK(cudaMalloc((void**)&d_filebufs[i], items[i].bytes.size()));
      CUDA_OK(cudaMemcpy(d_filebufs[i], items[i].bytes.data(),
                         items[i].bytes.size(), cudaMemcpyHostToDevice));
      h_ptrs[i]  = d_filebufs[i];
      h_sizes[i] = items[i].bytes.size();
    }
  }

  // device pointer arrays
  const uint8_t **d_ptrs = nullptr;
  size_t *d_sizes = nullptr;
  uint8_t *d_digests = nullptr;
  CUDA_OK(cudaMalloc((void**)&d_ptrs,  n*sizeof(uint8_t*)));
  CUDA_OK(cudaMalloc((void**)&d_sizes, n*sizeof(size_t)));
  CUDA_OK(cudaMalloc((void**)&d_digests, n*32));
  CUDA_OK(cudaMemcpy(d_ptrs,  h_ptrs.data(),  n*sizeof(uint8_t*), cudaMemcpyHostToDevice));
  CUDA_OK(cudaMemcpy(d_sizes, h_sizes.data(), n*sizeof(size_t),   cudaMemcpyHostToDevice));

  // launch: one block per file, 1 thread (SHA-256 is sequential per message)
  sha256_kernel<<<n,1>>>(d_ptrs, d_sizes, d_digests, n);
  CUDA_OK(cudaDeviceSynchronize());

  // collect
  std::vector<uint8_t> digests(n*32);
  CUDA_OK(cudaMemcpy(digests.data(), d_digests, n*32, cudaMemcpyDeviceToHost));

  // free device
  for (int i=0;i<n;++i) if (d_filebufs[i]) cudaFree(d_filebufs[i]);
  cudaFree(d_ptrs); cudaFree(d_sizes); cudaFree(d_digests);

  // compare and write report
  std::vector<std::string> got(n);
  int mism = 0;
  for (int i=0;i<n;++i){
    got[i] = to_hex(&digests[i*32], 32);
    if (strcasecmp(got[i].c_str(), items[i].expected.c_str()) != 0) mism++;
  }
  if (write_report(report_path, items, got, mism) != 0) return -1;
  if (out_mismatch_count) *out_mismatch_count = mism;
  return 0;
}
