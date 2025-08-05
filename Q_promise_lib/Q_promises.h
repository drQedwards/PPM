/**
 * Q_promises.h
 * Lightweight C "thenable" memory-chain simulator inspired by Kris Kowal's Q promises.
 * Part of the PPM/Q_promise_lib suite.
 *
 * Author: chatGPT-o3 (2025-08-05)
 */
#ifndef Q_PROMISES_H
#define Q_PROMISES_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>   /* for size_t */

/**
 * Singly-linked list node representing a step in the async memory chain.
 * `payload` can reference any NUL-terminated UTF-8 string.
 */
typedef struct QMemNode {
    long              index;      /* ordinal position in the chain          */
    const char       *payload;    /* arbitrary data (may be NULL)           */
    struct QMemNode  *next;       /* pointer to the next node               */
} QMemNode;

/** Function signature for callbacks used by q_then() */
typedef void (*QThenCallback)(long index, const char *payload);

/* Allocate and initialise a memory chain of `length` nodes.         */
QMemNode *q_mem_create_chain(size_t length);

/* Iterate through the chain, invoking `cb` for each node.           */
void q_then(QMemNode *head, QThenCallback cb);

/* Free the memory allocated by q_mem_create_chain().                */
void q_mem_free_chain(QMemNode *head);

#ifdef __cplusplus
}
#endif

#endif /* Q_PROMISES_H */
