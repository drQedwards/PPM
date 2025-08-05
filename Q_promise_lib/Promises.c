#include <stdio.h>
#include <stdlib.h>

typedef struct MemoryNode {
    int index;
    const char* data;
    struct MemoryNode* next;
} MemoryNode;

typedef void (*ThenCallback)(int index, const char* data);

// Simulate a memory chain
MemoryNode* init_memory_chain(int size) {
    MemoryNode* head = NULL;
    MemoryNode* prev = NULL;
    for (int i = 0; i < size; ++i) {
        MemoryNode* node = malloc(sizeof(MemoryNode));
        node->index = i;
        node->data = (i % 2 == 0) ? "Known" : "Unknown";
        node->next = NULL;
        if (prev)
            prev->next = node;
        else
            head = node;
        prev = node;
    }
    return head;
}

// Q.then equivalent
void q_then(MemoryNode* node, ThenCallback cb) {
    while (node) {
        cb(node->index, node->data);
        node = node->next;
    }
}

// Your callback
void memory_trace_callback(int index, const char* data) {
    printf("Resolved Memory[%d] → %s\n", index, data);
}

int main() {
    MemoryNode* memory = init_memory_chain(10);

    printf("Beginning memory trace:\n");
    q_then(memory, memory_trace_callback);

    // Clean up
    MemoryNode* tmp;
    while (memory) {
        tmp = memory;
        memory = memory->next;
        free(tmp);
    }

    return 0;
}
