
/*
 *  LLM-CLI-BUILDER-PPM.cpp
 *
 *  A tiny glue utility that combines:
 *    • Ollama CLI  — pulls / runs local GGUF models
 *    • PPM CLI     — installs Python deps (e.g. transformers, accelerate)
 *
 *  Usage:
 *      llm build <model> [--dep transformers==4.42.0 --dep accelerate]
 *      llm deps  <requirements.txt>
 *
 *  Build:
 *      g++ -std=c++17 -Iinclude -Llib -lppm_core -o llm LLM-CLI-BUILDER-PPM.cpp
 *
 *  Author: Dr. Josef K. Edwards  (c) 2025
 *  License: MIT
 */

#include <iostream>
#include <vector>
#include <string>
#include <cstdlib>
#include <getopt.h>

extern "C" {
    #include "CLI.h"   /* ppm_cli_run / ppm_cli_import */
}

static int run_cmd(const std::string &cmd, bool verbose)
{
    if (verbose)
        std::cout << ">> " << cmd << std::endl;
#ifdef _WIN32
    return system(cmd.c_str());
#else
    return std::system(cmd.c_str());
#endif
}

/* --------------------------------------------------------------- */

static int ollama_pull(const std::string &model, bool verbose)
{
    std::string cmd = "ollama pull " + model;
    return run_cmd(cmd, verbose);
}

static int ppm_import(const std::string &spec, bool verbose)
{
    return ppm_cli_import(spec.c_str(), verbose);
}

/* --------------------------------------------------------------- */

static void usage(const char *prog)
{
    std::cout <<
        "LLM CLI Builder – combines Ollama & PPM\n"
        "\n"
        "Usage: " << prog << " build <model> [--dep <spec>]... [--verbose]\n"
        "       " << prog << " deps  <file.txt> [--verbose]\n"
        "\n"
        "Options:\n"
        "  --dep <name[==ver]>   Extra Python deps to install via PPM\n"
        "  -v, --verbose         Chatty output\n"
        "  -h, --help            Show this help\n";
}

int main(int argc, char **argv)
{
    if (argc < 2) { usage(argv[0]); return 1; }

    std::string subcmd = argv[1];
    bool verbose = false;
    std::vector<std::string> deps;

    const struct option long_opts[] = {
        {"dep",     required_argument, 0, 'd'},
        {"verbose", no_argument,       0, 'v'},
        {"help",    no_argument,       0, 'h'},
        {0,0,0,0}
    };

    int opt, idx;
    /* start parsing after subcmd */
    optind = 2;
    while ((opt = getopt_long(argc, argv, "d:vh", long_opts, &idx)) != -1)
    {
        switch (opt) {
            case 'd': deps.emplace_back(optarg); break;
            case 'v': verbose = true; break;
            case 'h':
            default : usage(argv[0]); return 0;
        }
    }

    if (subcmd == "build")
    {
        if (optind >= argc) { std::cerr << "Error: model name missing\n"; return 1; }
        std::string model = argv[optind];

        /* 1) Pull model via Ollama */
        if (ollama_pull(model, verbose) != 0) {
            std::cerr << "Failed to pull model " << model << "\n";
            return 2;
        }

        /* default deps if none specified */
        if (deps.empty()) {
            deps = { "transformers", "accelerate", "sentencepiece" };
        }

        /* 2) Import Python deps via PPM */
        for (auto &d : deps) {
            if (ppm_import(d, verbose) != 0) {
                std::cerr << "Failed to import " << d << "\n";
                return 3;
            }
        }

        if (verbose)
            std::cout << "✔ Build complete. Ready to run: ollama run " << model << std::endl;
        return 0;
    }
    else if (subcmd == "deps")
    {
        if (optind >= argc) { std::cerr << "Error: requirements file missing\n"; return 1; }
        std::string file = argv[optind];

        /* read file line by line */
        FILE *fp = fopen(file.c_str(), "r");
        if (!fp) { perror("open requirements"); return 1; }

        char *line = nullptr;
        size_t n   = 0;
        ssize_t len;
        while ((len = getline(&line, &n, fp)) != -1) {
            if (len && line[len-1] == '\n') line[len-1] = 0;
            if (*line) deps.emplace_back(line);
        }
        free(line);
        fclose(fp);

        for (auto &d : deps) {
            if (ppm_import(d, verbose) != 0) {
                std::cerr << "Failed to import " << d << "\n";
                return 3;
            }
        }
        return 0;
    }
    else
    {
        usage(argv[0]);
        return 1;
    }
}
