 Transformer.c
// C implementation that embeds Python and calls into Transformer.py
#define PY_SSIZE_T_CLEAN
#include <Python.h>
#include <stdlib.h>
#include <string.h>
#include "Transformer.h"

struct TransformerHandle {
    PyObject* engine; // instance of Transformer.Engine
};

static void set_err(char* errbuf, size_t n, const char* msg){
    if(!errbuf || n==0) return;
    if(!msg) { errbuf[0]=0; return; }
    strncpy(errbuf, msg, n-1);
    errbuf[n-1] = 0;
}

static void fetch_py_error(char* errbuf, size_t n){
    if(!errbuf || n==0) { PyErr_Clear(); return; }
    PyObject *ptype=NULL, *pvalue=NULL, *ptrace=NULL;
    PyErr_Fetch(&ptype, &pvalue, &ptrace);
    PyErr_NormalizeException(&ptype, &pvalue, &ptrace);
    PyObject* s = pvalue ? PyObject_Str(pvalue) : NULL;
    const char* c = s ? PyUnicode_AsUTF8(s) : "Unknown Python error";
    set_err(errbuf, n, c);
    Py_XDECREF(s);
    Py_XDECREF(ptype);
    Py_XDECREF(pvalue);
    Py_XDECREF(ptrace);
}

static int ensure_py(char* errbuf, size_t n){
    if(!Py_IsInitialized()){
        Py_Initialize();
        if(!Py_IsInitialized()){
            set_err(errbuf, n, "Failed to initialize Python");
            return -1;
        }
        // Ensure sys.path includes current directory
        PyRun_SimpleString("import sys, os; sys.path.insert(0, os.getcwd())");
    }
    return 0;
}

TransformerHandle* transformer_init(const char* model_id,
                                    const char* device,
                                    int use_8bit,
                                    const char* embed_model_id,
                                    char* errbuf, size_t errbuf_sz){
    if(ensure_py(errbuf, errbuf_sz)) return NULL;

    PyObject* mod = PyImport_ImportModule("Transformer");
    if(!mod){
        fetch_py_error(errbuf, errbuf_sz);
        return NULL;
    }
    PyObject* cls = PyObject_GetAttrString(mod, "Engine");
    if(!cls){
        Py_DECREF(mod);
        fetch_py_error(errbuf, errbuf_sz);
        return NULL;
    }

    PyObject* py_model = model_id ? PyUnicode_FromString(model_id) : Py_None; if(model_id==NULL) Py_INCREF(Py_None);
    PyObject* py_dev   = device   ? PyUnicode_FromString(device)   : Py_None; if(device==NULL)   Py_INCREF(Py_None);
    PyObject* py_embed = embed_model_id ? PyUnicode_FromString(embed_model_id) : Py_None; if(embed_model_id==NULL) Py_INCREF(Py_None);
    PyObject* py_use8  = PyBool_FromLong(use_8bit ? 1 : 0);

    PyObject* args = PyTuple_New(0);
    PyObject* kwargs = PyDict_New();
    PyDict_SetItemString(kwargs, "model_id", py_model);
    PyDict_SetItemString(kwargs, "device", py_dev);
    PyDict_SetItemString(kwargs, "use_8bit", py_use8);
    PyDict_SetItemString(kwargs, "embed_model_id", py_embed);

    PyObject* engine = PyObject_Call(cls, args, kwargs);

    Py_DECREF(args); Py_DECREF(kwargs);
    Py_DECREF(py_model); Py_DECREF(py_dev); Py_DECREF(py_use8); Py_DECREF(py_embed);
    Py_DECREF(cls); Py_DECREF(mod);

    if(!engine){
        fetch_py_error(errbuf, errbuf_sz);
        return NULL;
    }

    TransformerHandle* h = (TransformerHandle*)calloc(1, sizeof(TransformerHandle));
    h->engine = engine;
    return h;
}

int transformer_generate(TransformerHandle* h,
                         const char* prompt,
                         int max_new_tokens,
                         float temperature,
                         char** out_text,
                         char* errbuf, size_t errbuf_sz){
    if(!h || !h->engine || !out_text){
        set_err(errbuf, errbuf_sz, "invalid arguments");
        return -1;
    }
    *out_text = NULL;

    PyObject* meth = PyObject_GetAttrString(h->engine, "generate");
    if(!meth){ fetch_py_error(errbuf, errbuf_sz); return -1; }

    PyObject* py_prompt = PyUnicode_FromString(prompt ? prompt : "");
    PyObject* py_mnt = PyLong_FromLong(max_new_tokens > 0 ? max_new_tokens : 128);
    PyObject* py_temp = PyFloat_FromDouble(temperature <= 0 ? 0.7 : temperature);

    PyObject* res = PyObject_CallFunctionObjArgs(meth, py_prompt, py_mnt, py_temp, NULL);
    Py_DECREF(meth); Py_DECREF(py_prompt); Py_DECREF(py_mnt); Py_DECREF(py_temp);

    if(!res){
        fetch_py_error(errbuf, errbuf_sz);
        return -1;
    }

    const char* s = PyUnicode_AsUTF8(res);
    if(!s){
        Py_DECREF(res);
        fetch_py_error(errbuf, errbuf_sz);
        return -1;
    }
    size_t L = strlen(s);
    char* out = (char*)malloc(L+1);
    memcpy(out, s, L+1);
    *out_text = out;
    Py_DECREF(res);
    return 0;
}

int transformer_embed(TransformerHandle* h,
                      const char* text,
                      float** out_vec,
                      size_t* out_len,
                      char* errbuf, size_t errbuf_sz){
    if(!h || !h->engine || !out_vec || !out_len){
        set_err(errbuf, errbuf_sz, "invalid arguments");
        return -1;
    }
    *out_vec = NULL; *out_len = 0;

    PyObject* meth = PyObject_GetAttrString(h->engine, "embed");
    if(!meth){ fetch_py_error(errbuf, errbuf_sz); return -1; }

    PyObject* py_text = PyUnicode_FromString(text ? text : "");
    PyObject* res = PyObject_CallFunctionObjArgs(meth, py_text, NULL);
    Py_DECREF(meth); Py_DECREF(py_text);

    if(!res){
        fetch_py_error(errbuf, errbuf_sz);
        return -1;
    }

    // Expect list[float]
    PyObject* seq = PySequence_Fast(res, "embedding must be a sequence");
    Py_DECREF(res);
    if(!seq){ fetch_py_error(errbuf, errbuf_sz); return -1; }

    Py_ssize_t n = PySequence_Fast_GET_SIZE(seq);
    float* vec = (float*)malloc(sizeof(float) * (size_t)n);
    for(Py_ssize_t i=0;i<n;i++){
        PyObject* item = PySequence_Fast_GET_ITEM(seq, i);
        vec[i] = (float)PyFloat_AsDouble(item);
    }
    Py_DECREF(seq);
    *out_vec = vec;
    *out_len = (size_t)n;
    return 0;
}

void transformer_free_text(char* p){ if(p) free(p); }
void transformer_free_vec(float* p){ if(p) free(p); }

void transformer_close(TransformerHandle* h){
    if(!h) return;
    if(h->engine){ Py_DECREF(h->engine); }
    free(h);
    // Do not call Py_Finalize() automatically; hosting app may manage Python.
}
