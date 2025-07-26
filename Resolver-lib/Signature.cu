// PEP-Signature.cu
//
// GPU-accelerated SHA-256 integrity + CPU Ed25519 signature verification (libsodium).
// - Hash each file on the GPU (one block per file) to produce SHA-256 digests.
// - Compare with expected SHA-256 from signatures.json.
// - Verify Ed25519 signatures on CPU (raw or Ed25519ph).
//
// Build example:
//   nvcc -O3 -std=c++17 -Xcompiler -fPIC -c PEP-Signature.cu -o PEP-Signature.o
//   g++  -shared -o libpep_signature.so PEP-Signature.o -lsodium -lcudart
//
// Public API declared at bottom: ir_signature_verify_cuda(...)

#include <cstdio>
#include <cstdlib>
#include <cstdint>
#include <cstring>
#include <string>
#include <vector>
#include <fstream>
#include <sstream>
#include <iostream>
#include <algorithm>

#include <cuda_runtime.h>
#include <sodium.h>

#include "importresolver.h"   // for declaration if you include the prototype there

// ---------------- CUDA helpers ----------------

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

  uint32_t H[8] = {
    0x6a09e667U,0xbb67ae85U,0x3c6ef372U,0xa54ff53aU,
    0x510e527fU,0x9b05688cU,0x1f83d9abU,0x5be0cd19U
  };

  size_t full = size / 64;
  sha256_blocks(data, full, H);

  // Tail + padding
  uint8_t tail[128];
  size_t tail_len = size - full*64;
  for (size_t i=0;i<tail_len;++i) tail[i] = data[full*64+i];
  tail[tail_len++] = 0x80;
  size_t pad_len = ((tail_len <= 56) ? (56 - tail_len) : (120 - tail_len));
  for (size_t i=0;i<pad_len;++i) tail[tail_len++] = 0x00;
  uint64_t bitlen = (uint64_t)size * 8ULL;
  for (int i=7;i>=0;--i) tail[tail_len++] = (uint8_t)((bitlen >> (i*8)) & 0xff);

  sha256_blocks(tail, tail_len/64, H);

  uint8_t *out = d_digests + idx*32;
  #pragma unroll
  for (int i=0;i<8;++i){
    out[i*4+0] = (uint8_t)((H[i] >> 24) & 0xff);
    out[i*4+1] = (uint8_t)((H[i] >> 16) & 0xff);
    out[i*4+2] = (uint8_t)((H[i] >> 8) & 0xff);
    out[i*4+3] = (uint8_t)( H[i]        & 0xff);
  }
}

// ---------------- host utilities ----------------

static std::string to_hex(const uint8_t *bytes, size_t n){
  static const char *h = "0123456789abcdef";
  std::string s; s.resize(n*2);
  for (size_t i=0;i<n;++i){
    s[2*i]   = h[(bytes[i]>>4)&0xf];
    s[2*i+1] = h[bytes[i]&0xf];
  }
  return s;
}

static inline int hexcasecmp(const std::string &a, const std::string &b){
  if (a.size() != b.size()) return (int)a.size() - (int)b.size();
  for (size_t i=0;i<a.size();++i){
    char ca = a[i], cb = b[i];
    if (ca>='A' && ca<='F') ca = (char)(ca - 'A' + 'a');
    if (cb>='A' && cb<='F') cb = (char)(cb - 'A' + 'a');
    if (ca != cb) return (int)ca - (int)cb;
  }
  return 0;
}

// minimal JSON parser helpers (tiny, assumes well-formed input)
static std::string slurp(const std::string &path){
  std::ifstream f(path, std::ios::binary);
  if (!f) return {};
  std::ostringstream ss; ss << f.rdbuf();
  return ss.str();
}

static std::string json_get_string(const std::string &src, const std::string &key, const std::string &defv=""){
  // naive `"key"\s*:\s*"value"`
  std::string pat = "\"" + key + "\"";
  size_t k = src.find(pat);
  if (k == std::string::npos) return defv;
  size_t q1 = src.find('"', src.find(':', k));
  if (q1 == std::string::npos) return defv;
  size_t q2 = src.find('"', q1+1);
  if (q2 == std::string::npos) return defv;
  return src.substr(q1+1, q2-(q1+1));
}

static bool json_iter_items(const std::string &src, std::vector<std::string> &items){
  // find `"items": [ ... ]`
  size_t pos = src.find("\"items\"");
  if (pos == std::string::npos) return false;
  size_t lb = src.find('[', pos);
  size_t rb = src.find(']', lb);
  if (lb == std::string::npos || rb == std::string::npos) return false;
  std::string arr = src.substr(lb+1, rb-lb-1);
  // split by "}," boundary (simple approach)
  size_t start = 0;
  while (start < arr.size()){
    size_t end = arr.find("},", start);
    std::string obj;
    if (end == std::string::npos) {
      obj = arr.substr(start);
      // ensure closing brace
      size_t br = obj.rfind('}');
      if (br != std::string::npos) obj = obj.substr(0, br+1);
      items.push_back(obj);
      break;
    } else {
      obj = arr.substr(start, end - start + 1);
      items.push_back(obj);
      start = end + 2;
    }
  }
  return true;
}

static bool json_item_get_string(const std::string &obj, const char *key, std::string &out){
  out = json_get_string(obj, key, "");
  return !out.empty();
}

static bool b64_decode(const std::string &b64, std::vector<unsigned char> &out){
  // use libsodium base64
  size_t maxlen = b64.size();
  out.resize(maxlen); // upper-bound
  size_t real_len = 0;
  if (sodium_base642bin(out.data(), out.size(),
                        b64.c_str(), b64.size(),
                        NULL, &real_len, NULL,
                        sodium_base64_VARIANT_ORIGINAL) != 0) {
    return false;
  }
  out.resize(real_len);
  return true;
}

struct SigItem {
  std::string filename;
  std::string expected_sha256;
  std::vector<unsigned char> pubkey; // 32
  std::vector<unsigned char> sig;    // 64
  std::vector<uint8_t> bytes;        // file bytes
};

static int load_signature_items(const char *root,
                                const char *signatures_json_path,
                                std::string &mode,
                                std::vector<SigItem> &items)
{
  std::string js = slurp(signatures_json_path);
  if (js.empty()) {
    fprintf(stderr, "[sig] cannot read %s\n", signatures_json_path);
    return -1;
  }
  // mode
  mode = json_get_string(js, "mode", "raw");
  std::vector<std::string> objs;
  if (!json_iter_items(js, objs)) {
    fprintf(stderr, "[sig] signatures.json missing 'items'\n");
    return -1;
  }

  for (auto &obj : objs){
    SigItem it;
    if (!json_item_get_string(obj, "filename", it.filename)) continue;
    json_item_get_string(obj, "sha256", it.expected_sha256);

    std::string pk_b64, sig_b64;
    json_item_get_string(obj, "pubkey", pk_b64);
    json_item_get_string(obj, "sig", sig_b64);
    if (pk_b64.empty() || sig_b64.empty()) {
      fprintf(stderr, "[sig] entry missing pubkey/sig for %s\n", it.filename.c_str());
      continue;
    }
    if (!b64_decode(pk_b64, it.pubkey) || it.pubkey.size() != crypto_sign_PUBLICKEYBYTES) {
      fprintf(stderr, "[sig] invalid pubkey for %s\n", it.filename.c_str());
      continue;
    }
    if (!b64_decode(sig_b64, it.sig) || it.sig.size() != crypto_sign_BYTES) {
      fprintf(stderr, "[sig] invalid signature for %s\n", it.filename.c_str());
      continue;
    }

    std::string full = std::string(root) + "/.ppm/cache/" + it.filename;
    std::ifstream f(full, std::ios::binary);
    if (!f) {
      fprintf(stderr, "[sig] missing cache file: %s\n", full.c_str());
      return -1;
    }
    f.seekg(0, std::ios::end);
    size_t sz = (size_t)f.tellg();
    f.seekg(0);
    it.bytes.resize(sz);
    if (sz) f.read((char*)it.bytes.data(), sz);

    items.emplace_back(std::move(it));
  }
  return 0;
}

static int write_report(const char *path,
                        const std::string &mode,
                        const std::vector<SigItem> &items,
                        const std::vector<std::string> &actual_sha256,
                        const std::vector<bool> &hash_ok,
                        const std::vector<bool> &sig_ok,
                        int invalid_sig_count,
                        int mismatch_count)
{
  std::ofstream out(path);
  if (!out) {
    fprintf(stderr, "[sig] cannot write %s\n", path);
    return -1;
  }
  out << "{\n";
  out << "  \"mode\": " << "\"" << mode << "\",\n";
  out << "  \"invalid_signatures\": " << invalid_sig_count << ",\n";
  out << "  \"hash_mismatches\": " << mismatch_count << ",\n";
  out << "  \"results\": [\n";
  for (size_t i=0;i<items.size();++i){
    out << "    {"
        << "\"filename\": \"" << items[i].filename << "\", "
        << "\"expected_sha256\": \"" << items[i].expected_sha256 << "\", "
        << "\"actual_sha256\": \"" << actual_sha256[i] << "\", "
        << "\"hash_ok\": " << (hash_ok[i] ? "true" : "false") << ", "
        << "\"sig_ok\": "  << (sig_ok[i]  ? "true" : "false")
        << "}";
    out << (i+1<items.size() ? ",\n" : "\n");
  }
  out << "  ]\n}\n";
  return 0;
}

// ---------------- public API ----------------

extern "C"
int ir_signature_verify_cuda(const char *root,
                             const char *signatures_json_path,
                             const char *report_json_path,
                             int *out_invalid_sig_count,
                             int *out_hash_mismatch_count)
{
  if (out_invalid_sig_count) *out_invalid_sig_count = -1;
  if (out_hash_mismatch_count) *out_hash_mismatch_count = -1;

  if (sodium_init() < 0) {
    fprintf(stderr, "[sig] libsodium init failed\n");
    return -1;
  }

  std::string mode;
  std::vector<SigItem> items;
  if (load_signature_items(root, signatures_json_path, mode, items) != 0) {
    return -1;
  }

  int n = (int)items.size();
  if (n == 0) {
    // write empty report
    std::ofstream out(report_json_path);
    if (out) {
      out << "{ \"mode\": \"" << mode << "\", \"invalid_signatures\": 0, \"hash_mismatches\": 0, \"results\": [] }\n";
    }
    if (out_invalid_sig_count) *out_invalid_sig_count = 0;
    if (out_hash_mismatch_count) *out_hash_mismatch_count = 0;
    return 0;
  }

  // Allocate device buffers & copy data
  std::vector<const uint8_t*> h_ptrs(n, nullptr);
  std::vector<size_t>         h_sizes(n, 0);
  std::vector<uint8_t*>       d_bufs(n, nullptr);

  for (int i=0;i<n;++i){
    if (!items[i].bytes.empty()){
      CUDA_OK(cudaMalloc((void**)&d_bufs[i], items[i].bytes.size()));
      CUDA_OK(cudaMemcpy(d_bufs[i], items[i].bytes.data(),
                         items[i].bytes.size(), cudaMemcpyHostToDevice));
      h_ptrs[i]  = d_bufs[i];
      h_sizes[i] = items[i].bytes.size();
    }
  }

  const uint8_t **d_ptrs = nullptr;
  size_t *d_sizes = nullptr;
  uint8_t *d_digests = nullptr;
  CUDA_OK(cudaMalloc((void**)&d_ptrs,  n*sizeof(uint8_t*)));
  CUDA_OK(cudaMalloc((void**)&d_sizes, n*sizeof(size_t)));
  CUDA_OK(cudaMalloc((void**)&d_digests, n*32));
  CUDA_OK(cudaMemcpy(d_ptrs,  h_ptrs.data(),  n*sizeof(uint8_t*), cudaMemcpyHostToDevice));
  CUDA_OK(cudaMemcpy(d_sizes, h_sizes.data(), n*sizeof(size_t),   cudaMemcpyHostToDevice));

  // Kernel: one block per file
  sha256_kernel<<<n,1>>>(d_ptrs, d_sizes, d_digests, n);
  CUDA_OK(cudaDeviceSynchronize());

  // Collect SHA-256
  std::vector<uint8_t> digests(n*32);
  CUDA_OK(cudaMemcpy(digests.data(), d_digests, n*32, cudaMemcpyDeviceToHost));

  // Free device memory
  for (int i=0;i<n;++i) if (d_bufs[i]) cudaFree(d_bufs[i]);
  cudaFree(d_ptrs); cudaFree(d_sizes); cudaFree(d_digests);

  // Compare hashes & verify signatures on CPU
  std::vector<std::string> actual(n);
  std::vector<bool> hash_ok(n, false), sig_ok(n, false);
  int mismatches = 0, invalid = 0;

  bool use_ph = (mode == "ph" || mode == "ed25519ph");

  for (int i=0;i<n;++i){
    actual[i] = to_hex(&digests[i*32], 32);
    if (!items[i].expected_sha256.empty() &&
        hexcasecmp(actual[i], items[i].expected_sha256) == 0){
      hash_ok[i] = true;
    } else {
      hash_ok[i] = false;
      mismatches++;
    }

    // Signature verification
    if (!use_ph) {
      // raw: signature over the full message
      if (crypto_sign_ed25519_verify_detached(
              items[i].sig.data(),
              items[i].bytes.data(), (unsigned long long)items[i].bytes.size(),
              items[i].pubkey.data()) == 0) {
        sig_ok[i] = true;
      } else {
        invalid++;
      }
    } else {
      // Ed25519ph: prehashed (SHA-512) mode
      crypto_sign_ed25519ph_state state;
      crypto_sign_ed25519ph_init(&state);
      crypto_sign_ed25519ph_update(&state, items[i].bytes.data(), (unsigned long long)items[i].bytes.size());
      if (crypto_sign_ed25519ph_final_verify(&state,
              items[i].sig.data(), items[i].pubkey.data()) == 0) {
        sig_ok[i] = true;
      } else {
        invalid++;
      }
    }
  }

  if (write_report(report_json_path, mode, items, actual, hash_ok, sig_ok, invalid, mismatches) != 0) {
    return -1;
  }

  if (out_invalid_sig_count)   *out_invalid_sig_count   = invalid;
  if (out_hash_mismatch_count) *out_hash_mismatch_count = mismatches;
  return 0;
}
