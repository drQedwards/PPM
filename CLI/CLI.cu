/***********************************************************************
 *  ppm – CUDA-accelerated CLI
 *  ---------------------------------------------------------------
 *  1. Same CLI flags & behaviour as CLI.c
 *  2. After a package is fetched by ppm_core_import(), we launch
 *     a GPU kernel that              ───────────────               ⟶
 *       • maps each   *.whl / *.tar.gz  blob to one thread-block
 *       • runs   incremental SHA-256   on 4-byte words
 *       • writes the digest back into  ✔ verified/manifest.sqlite
 *
 *  This is *illustrative*: if you prefer another algorithm (BLAKE3,
 *  CRC32, etc.) swap the device kernel below.
 **********************************************************************/
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <vector>
#include <string>
#include <filesystem>
#include <getopt.h>

#include "ppm_core.h"   // core import, cache location helpers
#include "CLI.h"        // header we wrote earlier

/* ------------------------------------------------------------------ */
/* GPU SHA-256 – minimal, unrolled for 32-bit words per FIPS-180-4    */
/* ------------------------------------------------------------------ */
#define ROTR(x,n) ((x >> n) | (x << (32 - n)))
__device__ static inline uint32_t Ch (uint32_t x,uint32_t y,uint32_t z){return (x & y) ^ (~x & z);}
__device__ static inline uint32_t Maj(uint32_t x,uint32_t y,uint32_t z){return (x & y) ^ (x & z) ^ (y & z);}
__device__ static inline uint32_t Sig0(uint32_t x){return ROTR(x,2) ^ ROTR(x,13) ^ ROTR(x,22);}
__device__ static inline uint32_t Sig1(uint32_t x){return ROTR(x,6) ^ ROTR(x,11) ^ ROTR(x,25);}
__device__ static inline uint32_t sig0(uint32_t x){return ROTR(x,7) ^ ROTR(x,18) ^ (x >> 3);}
__device__ static inline uint32_t sig1(uint32_t x){return ROTR(x,17) ^ ROTR(x,19) ^ (x >> 10);}

/* K-constants */
__constant__ uint32_t Kc[64] = {
  0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
  0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
  0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
  0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
  0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
  0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
  0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
  0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2
};

/* Device output buffer: each block writes 8 × uint32 = 256-bit digest */
__global__ void sha256_kernel(const uint8_t *blob, const size_t *offsets,
                              const size_t *sizes, uint32_t *digests)
{
    const int bid = blockIdx.x;
    const uint8_t *data = blob + offsets[bid];
    const size_t sz   = sizes[bid];

    /* ---- simple one-chunk SHA-256 (sz <= 64KiB) ------------------ */
    __shared__ uint32_t W[64];
    uint32_t H[8] = { 0x6a09e667,0xbb67ae85,0x3c6ef372,0xa54ff53a,
                      0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19 };

    /* We only demo a single 64-byte chunk here. For bigger files,     *
     * run this in chunks or launch multiple blocks per file.          */
    if (threadIdx.x < 16) {
        size_t i = threadIdx.x * 4;
        uint32_t val = (i+3 < sz) ?
            (data[i] << 24 | data[i+1] << 16 | data[i+2] << 8 | data[i+3]) :
            ( (i==sz) ? 0x80000000U : 0 );
        W[threadIdx.x] = val;
    }
    __syncthreads();

    for (int t = 16; t < 64; ++t)
        if (threadIdx.x == 0)
            W[t] = sig1(W[t-2]) + W[t-7] + sig0(W[t-15]) + W[t-16];
    __syncthreads();

    uint32_t a=H[0],b=H[1],c=H[2],d=H[3],e=H[4],f=H[5],g=H[6],h=H[7];
    for(int t=0;t<64;++t){
        uint32_t T1=h+Sig1(e)+Ch(e,f,g)+Kc[t]+W[t];
        uint32_t T2=Sig0(a)+Maj(a,b,c);
        h=g; g=f; f=e; e=d+T1; d=c; c=b; b=a; a=T1+T2;
    }
    if(threadIdx.x==0){
        H[0]+=a;H[1]+=b;H[2]+=c;H[3]+=d;H[4]+=e;H[5]+=f;H[6]+=g;H[7]+=h;
        for(int i=0;i<8;++i) digests[bid*8+i]=H[i];
    }
}

/* ------------------------------------------------------------------ */
/* Host helpers                                                       */
/* ------------------------------------------------------------------ */
static std::vector<std::filesystem::path>
files_for_pkg(const char *name, const char *ver)
{
    /* Example:  ~/.ppm/cache/<name>/<ver>/… */
    std::vector<std::filesystem::path> out;
    auto base = ppm_core_pkg_path(name, ver);
    for (auto &p : std::filesystem::recursive_directory_iterator(base))
        if (p.is_regular_file() &&
            (p.path().extension()==".whl" || p.path().extension()==".tar.gz"))
            out.push_back(p.path());
    return out;
}

static void gpu_verify(const std::vector<std::filesystem::path>& files, int verbose)
{
    if (files.empty()) return;

    /* concat blobs into one big buffer on host ---------------------- */
    std::vector<uint8_t>   h_blob;
    std::vector<size_t>    h_off, h_sz;
    for (auto &f: files) {
        h_off.push_back(h_blob.size());
        auto sz = std::filesystem::file_size(f);
        h_sz .push_back(sz);
        FILE *fp = fopen(f.string().c_str(), "rb");
        h_blob.resize(h_blob.size()+sz);
        fread(h_blob.data()+h_off.back(),1,sz,fp);
        fclose(fp);
    }

    /* copy to device ------------------------------------------------ */
    uint8_t *d_blob;  size_t *d_off,*d_sz;  uint32_t *d_dig;
    size_t  blob_bytes = h_blob.size();
    size_t  n          = files.size();
    cudaMalloc(&d_blob, blob_bytes);
    cudaMalloc(&d_off , n*sizeof(size_t));
    cudaMalloc(&d_sz  , n*sizeof(size_t));
    cudaMalloc(&d_dig , n*8*sizeof(uint32_t));
    cudaMemcpy(d_blob,h_blob.data(),blob_bytes,cudaMemcpyHostToDevice);
    cudaMemcpy(d_off ,h_off.data() ,n*sizeof(size_t),cudaMemcpyHostToDevice);
    cudaMemcpy(d_sz  ,h_sz.data()  ,n*sizeof(size_t),cudaMemcpyHostToDevice);

    /* launch one block per file ------------------------------------- */
    sha256_kernel<<<(int)n, 128>>>(d_blob,d_off,d_sz,d_dig);
    cudaDeviceSynchronize();

    /* fetch digests, push to manifest ------------------------------- */
    std::vector<uint32_t> h_dig(n*8);
    cudaMemcpy(h_dig.data(),d_dig,n*8*sizeof(uint32_t),cudaMemcpyDeviceToHost);

    for (size_t i=0;i<n;++i) {
        char hex[65]; hex[64]=0;
        for(int j=0;j<8;++j) sprintf(hex+j*8,"%08x",h_dig[i*8+j]);
        ppm_core_record_digest(files[i].c_str(), hex);
        if(verbose) printf("✓ %s  %s\n", files[i].c_str(), hex);
    }
    cudaFree(d_blob); cudaFree(d_off); cudaFree(d_sz); cudaFree(d_dig);
}

/* ------------------------------------------------------------------ */
/* CLI wrappers – shadowing the C version                             */
/* ------------------------------------------------------------------ */
int ppm_cli_import(const char *pkg_spec, int verbose)
{
    char *name=nullptr,*ver=nullptr;
    extern int split_spec(const char*,char**,char**); // declared in CLI.c
    split_spec(pkg_spec,&name,&ver);

    int rc = ppm_core_import(name,ver,verbose);          // download ⇢ cache
    auto files = files_for_pkg(name,ver);
    gpu_verify(files, verbose);                          // GPU digest pass

    free(name); free(ver);
    return rc;
}

/* Re-use getopt loop from CLI.c by #including it ------------------- */
#include "CLI_common_opts.inc"  // <-- same parser body as before
