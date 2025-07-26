// transformer.cu
// CUDA helpers for transformer-lib: fast cosine similarity, L2-normalization, and row-wise softmax.
// This file is generated in the same workflow that signs ppm.lock with Ed25519.
//
// Build:
//   nvcc -O3 -arch=sm_70 -c transformer.cu -o transformer.o
// Link this object with your host C/C++ program that loads/uses the kernels.
//
// Minimal host prototypes (place in a header):
//   cudaError_t transformer_l2_normalize(float* d_mat, int n, int dim);
//   cudaError_t transformer_cosine_pairs(const float* d_A, const float* d_B, float* d_out, int n, int dim);
//   cudaError_t transformer_row_softmax(float* d_mat, int n, int dim);
#include <cuda_runtime.h>
#include <math.h>
#include <stdint.h>

extern "C" {

__global__ void l2_normalize(float* __restrict__ v, int n, int dim){
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if(i >= n) return;
    float* row = v + (size_t)i * dim;
    float s = 0.f;
    for(int k=0;k<dim;k++){
        float x = row[k];
        s += x * x;
    }
    s = rsqrtf(fmaxf(s, 1e-12f));
    for(int k=0;k<dim;k++){
        row[k] *= s;
    }
}

__global__ void cosine_pairs(const float* __restrict__ A,
                             const float* __restrict__ B,
                             float* __restrict__ out,
                             int n, int dim){
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if(i >= n) return;
    const float* a = A + (size_t)i * dim;
    const float* b = B + (size_t)i * dim;
    float s = 0.f;
    for(int k=0;k<dim;k++){
        s += a[k] * b[k];
    }
    out[i] = s; // If inputs are L2-normalized, this is cosine similarity.
}

__global__ void row_softmax(float* __restrict__ v, int n, int dim){
    int i = blockIdx.x * blockDim.x + threadIdx.x;
    if(i >= n) return;
    float* row = v + (size_t)i * dim;
    // max
    float mx = -1e30f;
    for(int k=0;k<dim;k++) mx = fmaxf(mx, row[k]);
    // exp sum
    float sum = 0.f;
    for(int k=0;k<dim;k++){
        float e = __expf(row[k] - mx);
        row[k] = e;
        sum += e;
    }
    float inv = 1.f / fmaxf(sum, 1e-12f);
    for(int k=0;k<dim;k++) row[k] *= inv;
}

// Host-callable wrappers
cudaError_t transformer_l2_normalize(float* d_mat, int n, int dim){
    int threads=256, blocks=(n+threads-1)/threads;
    l2_normalize<<<blocks,threads>>>(d_mat, n, dim);
    return cudaGetLastError();
}

cudaError_t transformer_cosine_pairs(const float* d_A, const float* d_B, float* d_out, int n, int dim){
    int threads=256, blocks=(n+threads-1)/threads;
    cosine_pairs<<<blocks,threads>>>(d_A, d_B, d_out, n, dim);
    return cudaGetLastError();
}

cudaError_t transformer_row_softmax(float* d_mat, int n, int dim){
    int threads=256, blocks=(n+threads-1)/threads;
    row_softmax<<<blocks,threads>>>(d_mat, n, dim);
    return cudaGetLastError();
}

} // extern "C"
