// Transformer.h
// Minimal C API wrapper around a Python-based Hugging Face transformers engine.
// Build as a shared library and link against Python.
// Author: generated for Dr. Josef Kurk Edwards / John Trompeter
#ifndef TRANSFORMER_H
#define TRANSFORMER_H

#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

// Opaque handle to a Python-backed engine instance
typedef struct TransformerHandle TransformerHandle;

// Initialize the runtime and create an engine.
// model_id: HF model for generation (e.g., "gpt2" or "meta-llama/Llama-3.1-8B-Instruct")
// device: "auto", "cpu", "cuda", or specific index like "cuda:0"
// use_8bit: nonzero enables 8-bit loading where supported (ignored if not available)
// embed_model_id: optional; if NULL, defaults to "sentence-transformers/all-MiniLM-L6-v2"
// errbuf: optional buffer to receive error text on failure
TransformerHandle* transformer_init(const char* model_id,
                                    const char* device,
                                    int use_8bit,
                                    const char* embed_model_id,
                                    char* errbuf, size_t errbuf_sz);

// Generate text from a prompt.
// Returns 0 on success. On success, *out_text is malloc'd; call transformer_free_text().
int transformer_generate(TransformerHandle* h,
                         const char* prompt,
                         int max_new_tokens,
                         float temperature,
                         char** out_text,
                         char* errbuf, size_t errbuf_sz);

// Compute an embedding vector for text.
// Returns 0 on success. On success, *out_vec is malloc'd float array of length *out_len;
// caller must free with transformer_free_vec().
int transformer_embed(TransformerHandle* h,
                      const char* text,
                      float** out_vec,
                      size_t* out_len,
                      char* errbuf, size_t errbuf_sz);

// Release memory allocated by the library.
void transformer_free_text(char* p);
void transformer_free_vec(float* p);

// Destroy the engine and (optionally) finalize Python if no instances remain.
void transformer_close(TransformerHandle* h);

#ifdef __cplusplus
} // extern "C"
#endif

#endif // TRANSFORMER_Hp
