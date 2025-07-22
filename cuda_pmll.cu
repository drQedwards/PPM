// cuda_pmll.cu
//
// Persistent Memory Logic Loop (PMLL) CUDA Simulation
// Dr. Josef K. Edwards (Dr. Q) & Pandora (Fin)
// Build: nvcc -O3 -arch=sm_70 cuda_pmll.cu -o pmll_sim
//
#include <cstdio>
#include <cstdlib>
#include <curand_kernel.h>

#ifndef VECTOR_SIZE
#define VECTOR_SIZE 32
#endif

#ifndef MEMORY_CAPACITY
#define MEMORY_CAPACITY 512
#endif

#ifndef TOP_K
#define TOP_K 32
#endif

#ifndef DECAY_RATE
#define DECAY_RATE 0.97f
#endif

#ifndef PSI_ALPHA
#define PSI_ALPHA 0.1f
#endif

// ----------------------------------------------------------------------------
// Utility: device atomic max with index (for Top-K helpers)
// ----------------------------------------------------------------------------
struct SalienceIdx {
    float val;
    int   idx;
};

__device__ inline SalienceIdx atomicMaxSalience(SalienceIdx *address, SalienceIdx val) {
    SalienceIdx old = *address, assumed;
    unsigned long long int *addr_as_ull = (unsigned long long int*)address;
    unsigned long long int old_ull = *addr_as_ull, assumed_ull;

    do {
        assumed = old;
        if (val.val <= assumed.val) break;
        SalienceIdx newv = val;
        assumed_ull = old_ull;
        old_ull = atomicCAS(addr_as_ull, assumed_ull, *(unsigned long long int*)&newv);
        old = *(SalienceIdx*)&old_ull;
    } while (assumed_ull != old_ull);
    return old;
}

// ----------------------------------------------------------------------------
// psi_update: EMA reinforcement update
// ----------------------------------------------------------------------------
__device__ inline float psi_update(float current, float reward, float alpha = PSI_ALPHA){
    return (1.0f - alpha) * current + alpha * reward;
}

// ----------------------------------------------------------------------------
// Kernel: initialize RNG states
// ----------------------------------------------------------------------------
__global__ void init_rng(curandState *state, unsigned long seed){
    int id = threadIdx.x + blockIdx.x * blockDim.x;
    curand_init(seed, id, 0, &state[id]);
}

// ----------------------------------------------------------------------------
// Kernel: generate random reward and activation vectors
// ----------------------------------------------------------------------------
__global__ void generate_inputs(curandState *state, float *new_vectors, float *new_rewards, int n_new){
    int id = threadIdx.x + blockIdx.x * blockDim.x;
    if (id < n_new * VECTOR_SIZE){
        int vec_id = id / VECTOR_SIZE;
        curandState local = state[id];
        new_vectors[id] = curand_normal(&local);
        state[id] = local;
    }
    if (id < n_new){
        curandState local = state[id];
        new_rewards[id] = curand_uniform(&local);
        state[id] = local;
    }
}

// ----------------------------------------------------------------------------
// Kernel: decay & psi reinforcement for all existing memories
// ----------------------------------------------------------------------------
__global__ void update_salience(float *salience, float *rewards, int size){
    int id = threadIdx.x + blockIdx.x * blockDim.x;
    if (id < size){
        salience[id] *= DECAY_RATE;
        salience[id] = psi_update(salience[id], rewards[id]);
        if (salience[id] < 0.001f) salience[id] = 0.0f; // threshold
    }
}

// ----------------------------------------------------------------------------
// Kernel: insert new activations into memory (replace lowest salience)
//
// For simplicity: each new activation takes one slot chosen greedily on CPU.
// For full GPU parallelism, implement a parallel selection of lowest saliences.
// ----------------------------------------------------------------------------
__global__ void write_activation(float *memory, float *salience, 
                                 const float *new_vec, float new_sal, int slot){
    // write vector
    int id = threadIdx.x + blockIdx.x * blockDim.x;
    if (id < VECTOR_SIZE){
        memory[slot * VECTOR_SIZE + id] = new_vec[id];
    }
    if (id == 0) salience[slot] = new_sal;
}

// ----------------------------------------------------------------------------
// Host helper: find lowest salience slot (CPU side for brevity)
// ----------------------------------------------------------------------------
int find_lowest_slot(const float *sal, int capacity){
    int idx = 0;
    float minv = sal[0];
    for (int i=1; i<capacity; ++i){
        if (sal[i] < minv){
            minv = sal[i];
            idx = i;
        }
    }
    return idx;
}

// ----------------------------------------------------------------------------
// Host side driver (example). You can wrap this in extern "C" for Python FFI.
// ----------------------------------------------------------------------------
int main(){
    const int steps = 256;
    const int n_new_per_step = 4;

    // Allocate host memory
    size_t mem_bytes = MEMORY_CAPACITY * VECTOR_SIZE * sizeof(float);
    size_t sal_bytes = MEMORY_CAPACITY * sizeof(float);
    float *h_memory = (float*)calloc(mem_bytes, 1);
    float *h_sal    = (float*)calloc(sal_bytes, 1);
    float *h_rewards= (float*)calloc(sal_bytes, 1);

    // Allocate device memory
    float *d_memory, *d_sal, *d_rewards;
    cudaMalloc(&d_memory, mem_bytes);
    cudaMalloc(&d_sal,    sal_bytes);
    cudaMalloc(&d_rewards,sal_bytes);
    cudaMemcpy(d_memory, h_memory, mem_bytes, cudaMemcpyHostToDevice);
    cudaMemcpy(d_sal,    h_sal,    sal_bytes, cudaMemcpyHostToDevice);

    // RNG
    curandState *d_state;
    cudaMalloc(&d_state, sizeof(curandState) * MEMORY_CAPACITY * VECTOR_SIZE);
    init_rng<<<(MEMORY_CAPACITY*VECTOR_SIZE+255)/256, 256>>>(d_state, 1337UL);

    // Temp buffers for new inputs
    float *d_new_vecs, *d_new_rewards;
    cudaMalloc(&d_new_vecs, n_new_per_step * VECTOR_SIZE * sizeof(float));
    cudaMalloc(&d_new_rewards, n_new_per_step * sizeof(float));

    dim3 block(256);
    for (int t = 0; t < steps; ++t){
        // 1) generate n_new_per_step new activations
        int total_threads = max(n_new_per_step * VECTOR_SIZE, n_new_per_step);
        dim3 grid((total_threads + block.x - 1)/block.x);
        generate_inputs<<<grid, block>>>(d_state, d_new_vecs, d_new_rewards, n_new_per_step);

        // 2) update salience of all existing memories
        dim3 grid2((MEMORY_CAPACITY + block.x - 1)/block.x);
        update_salience<<<grid2, block>>>(d_sal, d_rewards, MEMORY_CAPACITY);

        // Pull rewards + salience to host for greedy slot replacement
        cudaMemcpy(h_sal, d_sal, sal_bytes, cudaMemcpyDeviceToHost);
        cudaMemcpy(h_rewards, d_new_rewards, n_new_per_step * sizeof(float), cudaMemcpyDeviceToHost);

        for (int i = 0; i < n_new_per_step; ++i){
            // copy single new vector to host for convenience
            float temp_vec[VECTOR_SIZE];
            cudaMemcpy(temp_vec, d_new_vecs + i * VECTOR_SIZE, VECTOR_SIZE * sizeof(float), cudaMemcpyDeviceToHost);

            int slot = find_lowest_slot(h_sal, MEMORY_CAPACITY);
            // write back on device
            float *d_single_vec = d_new_vecs + i * VECTOR_SIZE;
            write_activation<<<(VECTOR_SIZE+255)/256, 256>>>(d_memory, d_sal, d_single_vec, h_rewards[i], slot);

            // Update our host cache
            h_sal[slot] = h_rewards[i];
        }
    }

    // Dump final salience
    cudaMemcpy(h_sal, d_sal, sal_bytes, cudaMemcpyDeviceToHost);
    for (int i=0;i<10;i++){
        printf("sal[%d]=%f\n", i, h_sal[i]);
    }

    cudaFree(d_memory);
    cudaFree(d_sal);
    cudaFree(d_rewards);
    cudaFree(d_state);
    cudaFree(d_new_vecs);
    cudaFree(d_new_rewards);
    free(h_memory);
    free(h_sal);
    free(h_rewards);

    return 0;
}
