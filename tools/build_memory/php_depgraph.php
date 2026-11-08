#!/usr/bin/env php
<?php
/**
 * php-depgraph.php — defensive PHP dependency graph for PMLL build_memory.
 *
 * Walks a PHP project with token_get_all (no deps) and writes:
 *  - units JSON (same shape as go_batch_build.py output: {"units":[...],"meta":{...}})
 *    one unit per .php file; depends_on_units = files reached via require/include
 *    or via `use`/`new`/`extends`/`implements` of a class declared in the project.
 *    ok = `php -l` lint result. Feed to tools/build_memory/build_to_memory.py.
 *  - --graph FILE: symbol-level graph {nodes,edges} with PMLL-style (type,label) keys:
 *    namespaces, classes, functions, iterators (Iterator/IteratorAggregate/Generator)
 *    as first-class nodes, call edges, and audit flags (eval/unserialize/dynamic include).
 * Read-only on the target project. Usage:
 *   php php-depgraph.php /path/to/project --out php_build_results.json --graph php_graph.json [--no-lint]
 */
$argv0 = array_shift($argv);
$root = null; $out = 'php_build_results.json'; $graphOut = null; $lint = true;
for ($i = 0; $i < count($argv); $i++) {
    $a = $argv[$i];
    if ($a === '--out') $out = $argv[++$i];
    elseif ($a === '--graph') $graphOut = $argv[++$i];
    elseif ($a === '--no-lint') $lint = false;
    else $root = $a;
}
if (!$root || !is_dir($root)) { fwrite(STDERR, "usage: $argv0 <project> [--out f] [--graph f] [--no-lint]\n"); exit(2); }
$root = realpath($root);
$SKIP = '#/(vendor|node_modules|\.git)/#';

$files = [];
$it = new RecursiveIteratorIterator(new RecursiveDirectoryIterator($root, FilesystemIterator::SKIP_DOTS));
foreach ($it as $f) {
    $p = $f->getPathname();
    if (substr($p, -4) !== '.php' || preg_match($SKIP, $p)) continue;
    $files[] = substr($p, strlen($root) + 1);
}
sort($files);

$nodes = []; $edges = [];
function node(&$nodes, $type, $label, $content, $meta = []) { $nodes["$type\0$label"] = compact('type','label','content') + ['metadata' => $meta]; }
function edge(&$edges, $src, $rel, $dst) { $edges["$src\0$rel\0$dst"] = ['source' => $src, 'relation' => $rel, 'target' => $dst]; }

$ITER = ['Iterator','IteratorAggregate','Traversable','Generator','SeekableIterator','OuterIterator','RecursiveIterator'];
$classFile = []; $fileInfo = [];
$sig = fn($t) => is_array($t) ? $t[0] : null;
$txt = fn($t) => is_array($t) ? $t[1] : $t;
$NAME = [T_STRING, T_NAME_QUALIFIED, T_NAME_FULLY_QUALIFIED, T_NAME_RELATIVE];

foreach ($files as $rel) {
    $src = file_get_contents("$root/$rel");
    $toks = array_values(array_filter(@token_get_all($src), fn($t) => !in_array($GLOBALS['sig']($t), [T_WHITESPACE, T_COMMENT, T_DOC_COMMENT], true)));
    $ns = ''; $uses = []; $info = ['classes'=>[], 'functions'=>[], 'includes'=>[], 'dyn_includes'=>0, 'refs'=>[], 'calls'=>[], 'audit'=>[]];
    $curFn = null; $curClass = null; $depth = 0; $fnDepth = -1; $classDepth = -1;
    $resolve = function ($n) use (&$ns, &$uses) {
        if ($n === '' ) return $n;
        if ($n[0] === '\\') return ltrim($n, '\\');
        $first = explode('\\', $n)[0];
        if (isset($uses[strtolower($first)])) return $uses[strtolower($first)] . substr($n, strlen($first));
        if (in_array(strtolower($n), ['self','static','parent'])) return $n;
        return $ns ? "$ns\\$n" : $n;
    };
    $n = count($toks);
    for ($i = 0; $i < $n; $i++) {
        $t = $toks[$i]; $k = $sig($t);
        if ($t === '{' || $k === T_CURLY_OPEN || $k === T_DOLLAR_OPEN_CURLY_BRACES) { $depth++; continue; }
        if ($t === '}') { $depth--; if ($depth === $fnDepth) { $curFn = null; $fnDepth = -1; } if ($depth === $classDepth) { $curClass = null; $classDepth = -1; } continue; }
        if ($k === T_NAMESPACE && in_array($sig($toks[$i+1] ?? null), $NAME, true)) {
            $ns = $txt($toks[$i+1]); node($nodes, 'concept', "php:ns:$ns", "namespace $ns"); edge($edges, "php:ns:$ns", 'contains', "php:file:$rel");
        } elseif ($k === T_USE && $depth === 0) {
            $j = $i + 1; if (in_array(strtolower($txt($toks[$j])), ['function','const'])) $j++;
            while ($j < $n && $toks[$j] !== ';') {
                if (in_array($sig($toks[$j]), $NAME, true)) {
                    $full = ltrim($txt($toks[$j]), '\\'); $alias = basename(str_replace('\\','/',$full));
                    if ($sig($toks[$j+1] ?? null) === T_AS) { $alias = $txt($toks[$j+2]); $j += 2; }
                    $uses[strtolower($alias)] = $full; $info['refs'][] = $full;
                }
                $j++;
            }
        } elseif (in_array($k, [T_CLASS, T_INTERFACE, T_TRAIT, T_ENUM], true) && $sig($toks[$i+1] ?? null) === T_STRING && $sig($toks[$i-1] ?? null) !== T_DOUBLE_COLON && $sig($toks[$i-1] ?? null) !== T_NEW) {
            $cn = ($ns ? "$ns\\" : '') . $txt($toks[$i+1]); $kind = strtolower($txt($t));
            $curClass = $cn; $classDepth = $depth;
            $parents = []; $j = $i + 2;
            while ($j < $n && $toks[$j] !== '{') { if (in_array($sig($toks[$j]), $NAME, true)) $parents[] = $resolve($txt($toks[$j])); $j++; }
            $isIter = (bool)array_intersect(array_map(fn($p) => ltrim($p, '\\'), $parents), $ITER) || in_array(basename(str_replace('\\','/',$cn)), $ITER);
            node($nodes, 'concept', "php:class:$cn", "$kind $cn", ['kind'=>$kind, 'file'=>$rel, 'iterator'=>$isIter]);
            edge($edges, "php:file:$rel", 'contains', "php:class:$cn");
            if ($ns) edge($edges, "php:ns:$ns", 'contains', "php:class:$cn");
            foreach ($parents as $p) { edge($edges, "php:class:$cn", 'depends_on', "php:class:$p"); $info['refs'][] = $p;
                if (in_array(ltrim($p,'\\'), $ITER)) { node($nodes, 'concept', "php:iter:$p", "builtin iterator interface $p", ['iterator'=>true]); edge($edges, "php:class:$cn", 'implements_iterator', "php:iter:$p"); } }
            if ($isIter) { node($nodes, 'concept', "php:iter:$cn", "iterator class $cn", ['iterator'=>true,'file'=>$rel]); edge($edges, "php:iter:$cn", 'references', "php:class:$cn"); }
            $classFile[strtolower($cn)] = $rel; $info['classes'][] = $cn;
        } elseif ($k === T_FUNCTION) {
            $j = $i + 1; if ($toks[$j] === '&') $j++;
            if ($sig($toks[$j] ?? null) === T_STRING) {
                $fn = $curClass ? "$curClass::" . $txt($toks[$j]) : (($ns ? "$ns\\" : '') . $txt($toks[$j]));
                // generator detection: scan body for yield
                $b = $j; while ($b < $n && $toks[$b] !== '{' && $toks[$b] !== ';') $b++;
                $gen = false; if ($toks[$b] === '{') { $d = 0; for ($q = $b; $q < $n; $q++) { if ($toks[$q] === '{' || in_array($sig($toks[$q]), [T_CURLY_OPEN, T_DOLLAR_OPEN_CURLY_BRACES], true)) $d++; elseif ($toks[$q] === '}') { if (--$d === 0) break; } elseif (in_array($sig($toks[$q]), [T_YIELD, T_YIELD_FROM], true)) { $gen = true; } } }
                node($nodes, 'concept', "php:fn:$fn", "function $fn", ['file'=>$rel, 'generator'=>$gen]);
                edge($edges, $curClass ? "php:class:$curClass" : "php:file:$rel", 'contains', "php:fn:$fn");
                if ($gen) { node($nodes, 'concept', "php:iter:$fn", "generator $fn", ['iterator'=>true,'generator'=>true,'file'=>$rel]); edge($edges, "php:iter:$fn", 'references', "php:fn:$fn"); }
                $info['functions'][] = $fn;
                if ($toks[$b] === '{') { $curFn = $fn; $fnDepth = $depth; }
            }
        } elseif (in_array($k, [T_REQUIRE, T_REQUIRE_ONCE, T_INCLUDE, T_INCLUDE_ONCE], true)) {
            // static resolution of 'x.php' or __DIR__ . '/x.php'
            $j = $i + 1; if ($toks[$j] === '(') $j++;
            $parts = []; $static = true;
            while ($j < $n && $toks[$j] !== ';' && $toks[$j] !== ')') {
                $s = $sig($toks[$j]);
                if ($s === T_DIR) $parts[] = dirname("$root/$rel");
                elseif ($s === T_CONSTANT_ENCAPSED_STRING) $parts[] = trim($txt($toks[$j]), "'\"");
                elseif ($toks[$j] !== '.') $static = false;
                $j++;
            }
            $target = null;
            if ($static && $parts) { $p = implode('', $parts); if ($p[0] !== '/') $p = dirname("$root/$rel") . "/$p"; $rp = realpath($p); if ($rp && str_starts_with($rp, "$root/")) $target = substr($rp, strlen($root) + 1); }
            if ($target) $info['includes'][] = $target; else { $info['dyn_includes']++; $info['audit'][] = 'dynamic_include'; }
        } elseif ($k === T_EVAL) { $info['audit'][] = 'eval';
        } elseif ($k === T_NEW && in_array($sig($toks[$i+1] ?? null), $NAME, true)) {
            $c = $resolve($txt($toks[$i+1])); $info['refs'][] = $c;
            if ($curFn) edge($edges, "php:fn:$curFn", 'calls', "php:class:$c");
        } elseif (in_array($k, $NAME, true) && ($toks[$i+1] ?? null) === '(' && !in_array($sig($toks[$i-1] ?? null), [T_FUNCTION, T_OBJECT_OPERATOR, T_NULLSAFE_OBJECT_OPERATOR, T_NEW], true)) {
            $name = $txt($t);
            if ($sig($toks[$i-1] ?? null) === T_DOUBLE_COLON) { $cls = $resolve($txt($toks[$i-2])); if ($cls === 'self' || $cls === 'static') $cls = $curClass; $callee = "$cls::$name"; $info['refs'][] = $cls; }
            else { $callee = ltrim($name, '\\'); if (in_array(strtolower($callee), ['unserialize','assert','create_function','system','exec','shell_exec','passthru','proc_open','popen'])) $info['audit'][] = strtolower($callee); }
            if ($curFn) $info['calls'][] = [$curFn, $callee];
        }
    }
    $fileInfo[$rel] = $info;
}

// resolve calls to declared functions only (unresolved builtins dropped from edges)
$declared = []; foreach ($nodes as $nd) if (str_starts_with($nd['label'], 'php:fn:')) $declared[strtolower(substr($nd['label'], 7))] = $nd['label'];
$units = [];
foreach ($fileInfo as $rel => $info) {
    $deps = $info['includes'];
    foreach ($info['refs'] as $r) { $r = strtolower(ltrim($r, '\\')); if (isset($classFile[$r]) && $classFile[$r] !== $rel) $deps[] = $classFile[$r]; }
    foreach ($info['calls'] as [$from, $callee]) {
        $c = strtolower($callee); $ns = strtolower(implode('\\', array_slice(explode('\\', $from), 0, -1)));
        $hit = $declared[$c] ?? $declared["$ns\\$c"] ?? null;
        if ($hit) edge($edges, "php:fn:$from", 'calls', $hit);
    }
    foreach ($info['includes'] as $t) edge($edges, "php:file:$rel", 'includes', "php:file:$t");
    $deps = array_values(array_unique(array_diff($deps, [$rel]))); sort($deps);
    $audit = array_count_values($info['audit']);
    node($nodes, 'file', "php:file:$rel", "php file $rel", ['audit' => $audit]);
    $ok = null; $errs = [];
    if ($lint) { exec('php -l ' . escapeshellarg("$root/$rel") . ' 2>&1', $o, $rc); $ok = $rc === 0; if (!$ok) $errs = array_slice(array_filter($o, fn($l) => !str_starts_with($l, 'Errors parsing')), 0, 5); unset($o); }
    $units[] = ['path'=>$rel, 'module'=>basename($root), 'sha256'=>hash_file('sha256', "$root/$rel"), 'files'=>[$rel],
        'includes'=>[], 'depends_on_units'=>$deps, 'kind'=>'php', 'required'=>false, 'ok'=>$ok, 'build_ok'=>$ok,
        'warnings'=>array_sum($audit), 'first_errors'=>$errs, 'audit'=>$audit,
        'classes'=>$info['classes'], 'functions'=>$info['functions']];
}
// root entry point: composer.json "bin", else index.php / public/index.php, else file with most deps
$rootEntry = null; $cj = @json_decode(@file_get_contents("$root/composer.json"), true);
foreach ((array)($cj['bin'] ?? []) as $b) if (is_file("$root/$b")) { $rootEntry = $b; break; }
foreach ((array)($cj['autoload']['files'] ?? []) as $b) if (!$rootEntry && is_file("$root/$b")) $rootEntry = $b;
foreach (['index.php','public/index.php','src/index.php'] as $c) if (!$rootEntry && is_file("$root/$c")) $rootEntry = $c;
if (!$rootEntry && $units) { $best = null; foreach ($units as $u) if (!preg_match('#(^|/)tests?/#i', $u['path'])) if (!$best || count($u['depends_on_units']) > count($best['depends_on_units'])) $best = $u; $rootEntry = $best['path']; }
$rootLabel = 'php:root:' . basename($root);
node($nodes, 'note', $rootLabel, "root entry point $rootEntry", ['entry' => $rootEntry]);
edge($edges, $rootLabel, 'references', "php:file:$rootEntry");
if (!isset($nodes["file\0php:file:$rootEntry"])) node($nodes, 'file', "php:file:$rootEntry", "php file $rootEntry (non-.php entry)");

// drop edges whose endpoints don't exist (e.g. external classes) except keep them as external concept nodes
foreach ($edges as $e) foreach ([$e['source'], $e['target']] as $l) {
    $have = false; foreach (['concept','file','note'] as $ty) if (isset($nodes["$ty\0$l"])) { $have = true; break; }
    if (!$have) node($nodes, 'concept', $l, "external $l", ['external' => true]);
}
$head = trim((string)@shell_exec('git -C ' . escapeshellarg($root) . ' rev-parse HEAD 2>/dev/null'));
$meta = ['repo'=>basename($root), 'module'=>basename($root), 'head'=>$head, 'generated_at'=>date('c'), 'php'=>PHP_VERSION,
         'root_entry'=>$rootEntry, 'parser'=>'token_get_all', 'lint'=>$lint];
file_put_contents($out, json_encode(['units'=>$units, 'required_failures'=>0, 'meta'=>$meta], JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES));
$g = ['meta'=>$meta, 'root'=>$rootLabel, 'nodes'=>array_values($nodes), 'edges'=>array_values($edges)];
if ($graphOut) file_put_contents($graphOut, json_encode($g, JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES));
$cnt = []; foreach ($nodes as $nd) { $p = explode(':', $nd['label'])[1]; $cnt[$p] = ($cnt[$p] ?? 0) + 1; }
$ec = array_count_values(array_column(array_values($edges), 'relation'));
ksort($cnt); ksort($ec);
fwrite(STDERR, sprintf("files=%d nodes=%d edges=%d root=%s\nnode kinds: %s\nedge kinds: %s\n", count($units), count($nodes), count($edges), $rootEntry, json_encode($cnt), json_encode($ec)));
