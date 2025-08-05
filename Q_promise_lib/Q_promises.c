/**
 * Q_promises.c
 * Implementation of the lightweight thenable memory-chain simulator.
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "Q_promises.h"

/* Helper to duplicate string safely */
static char *str_dup(const char *src) {
    if (!src) return NULL;
    size_t len = strlen(src) + 1;
    char *copy = (char *)malloc(len);
    if (copy) memcpy(copy, src, len);
    return copy;
}

QMemNode *q_mem_create_chain(size_t length) {
    if (length == 0) return NULL;

    QMemNode *head = NULL, *prev = NULL;

    for (size_t i = 0; i < length; ++i) {
        QMemNode *node = (QMemNode *)malloc(sizeof(QMemNode));
        if (!node) {
            /* OOM -- clean up any allocated nodes */
            q_mem_free_chain(head);
            return NULL;
        }
        node->index   = (long)i;
        node->payload = (i % 2 == 0) ? str_dup("Known") : str_dup("Unknown");
        node->next    = NULL;

        if (prev)
            prev->next = node;
        else
            head = node;

        prev = node;
    }
    return head;
}

void q_then(QMemNode *head, QThenCallback cb) {
    if (!cb) return;
    for (QMemNode *node = head; node; node = node->next) {
        cb(node->index, node->payload);
    }
}

void q_mem_free_chain(QMemNode *head) {
    while (head) {
        QMemNode *next = head->next;
        free((char *)head->payload);
        free(head);
        head = next;
    }
}
