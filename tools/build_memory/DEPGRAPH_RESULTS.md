# Measured runs (2026-10-22, PHP 8.4.26, Node on Debian 13)

| repo | files | graph nodes / edges | build_to_memory nodes / edges / silo keys |
|---|---|---|---|
| nikic/FastRoute (PHP) | 47 | 397 / 678 | 98 / 238 / 47 |
| phantom/phantom-connect-sdk (JS/TS, 32 packages) | 570 | 1421 / 3079 | 68 / 188 / 32 |
| phantom/react-native-wallet-sdk-demo-app | 8 | 20 / 27 | not loaded |

FastRoute: root `src/functions.php`; 55 classes, 271 functions, 13 namespaces, 10 iterator nodes
(all generators in benchmark/test files); edges: calls 206, contains 426, depends_on 35,
references 11; `php -l` 47/47 OK; audit flags: 1 non-static include (`src/Cache/FileCache.php`), `assert` calls.
phantom-connect-sdk: imports 1771, exports 737, contains 570; 70 external packages; no
generator/iterator implementations detected by the regex scanner.
