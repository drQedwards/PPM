<?php
// PMLL anchor: SHA-256 digests only (payloads stay off-chain) -> PmllAnchor.store(id, root)
// Usage: php anchor.php --rpc URL --contract 0xADDR --from 0xADMIN [--dry]
//   Sends via eth_sendTransaction (unlocked dev/anvil account), then verifies the
//   Anchor event in the receipt and get(id) read-back. Uses `cast` only for keccak.
$o = getopt('', ['rpc:', 'contract:', 'from:', 'dry', 'out:']);
$W = '/workspace';
$CAST = getenv('CAST') ?: (getenv('HOME') . '/.foundry/bin/cast');

function git_tree($repo) { return trim(shell_exec("git -C " . escapeshellarg($repo) . " rev-parse 'HEAD^{tree}'")); }
$leaves = [];
foreach (glob("$W/php-depgraph/out/*_{units,graph}.json", GLOB_BRACE) as $f)
  $leaves['file:' . basename($f)] = hash_file('sha256', $f);
$leaves['tree:pmll@feat/php-js-depgraph'] = hash('sha256', git_tree("$W/pmll-main"));
$leaves['tree:ppm@feat/php-js-depgraph']  = hash('sha256', git_tree("$W/ppm-main"));
$leaves['file:php-depgraph/README.md']    = hash_file('sha256', "$W/php-depgraph/README.md");
ksort($leaves);

// Merkle: leaf = sha256(0x00||label||0x00||digest), node = sha256(0x01||a||b), odd node promoted
$lvl = [];
foreach ($leaves as $k => $d) $lvl[] = hash('sha256', "\x00$k\x00" . hex2bin($d), true);
while (count($lvl) > 1) {
  $n = [];
  for ($i = 0; $i < count($lvl); $i += 2)
    $n[] = isset($lvl[$i+1]) ? hash('sha256', "\x01" . $lvl[$i] . $lvl[$i+1], true) : $lvl[$i];
  $lvl = $n;
}
$root = '0x' . bin2hex($lvl[0]);
$id = '0x' . hash('sha256', 'pmll:depgraph:feat/php-js-depgraph:items1-3');
$manifest = ['id' => $id, 'root' => $root, 'leaves' => $leaves];
file_put_contents($o['out'] ?? "$W/php-depgraph/out/anchor_manifest.json", json_encode($manifest, JSON_PRETTY_PRINT|JSON_UNESCAPED_SLASHES));
echo "id   $id\nroot $root\nleaves " . count($leaves) . "\n";
if (isset($o['dry'])) exit(0);

$rpc = $o['rpc']; $to = strtolower($o['contract']); $from = $o['from'];
function rpc($url, $m, $p) {
  $c = curl_init($url);
  curl_setopt_array($c, [CURLOPT_POST => 1, CURLOPT_RETURNTRANSFER => 1, CURLOPT_HTTPHEADER => ['Content-Type: application/json'],
    CURLOPT_POSTFIELDS => json_encode(['jsonrpc' => '2.0', 'id' => 1, 'method' => $m, 'params' => $p])]);
  $r = json_decode(curl_exec($c), true);
  if (isset($r['error'])) { fwrite(STDERR, "$m: " . json_encode($r['error']) . "\n"); exit(1); }
  return $r['result'];
}
$sel = fn($sig) => substr(trim(shell_exec(escapeshellarg($GLOBALS['CAST']) . ' keccak ' . escapeshellarg($sig))), 0, 10);
$w = fn($h) => str_pad(substr($h, 2), 64, '0', STR_PAD_LEFT);
$data = $sel('store(bytes32,bytes32)') . $w($id) . $w($root);   // ABI: selector || id || commitment
$tx = rpc($rpc, 'eth_sendTransaction', [['from' => $from, 'to' => $to, 'data' => $data]]);
echo "tx   $tx\n";
for ($i = 0; $i < 60 && !($rc = rpc($rpc, 'eth_getTransactionReceipt', [$tx])); $i++) sleep(1);
$topic0 = trim(shell_exec(escapeshellarg($CAST) . ' keccak ' . escapeshellarg('Anchor(bytes32,bytes32)')));
$ok_ev = false;
foreach ($rc['logs'] as $l)
  if (strtolower($l['address']) === $to && $l['topics'][0] === $topic0 && $l['topics'][1] === $id && strtolower($l['data']) === $root) $ok_ev = true;
$ret = rpc($rpc, 'eth_call', [['to' => $to, 'data' => $sel('get(bytes32)') . $w($id)], 'latest']);
$ok_rd = substr($ret, 2, 64) === str_pad('1', 64, '0', STR_PAD_LEFT) && '0x' . substr($ret, 66, 64) === $root;
echo "block " . hexdec($rc['blockNumber']) . " status {$rc['status']}\n";
echo "event " . ($ok_ev ? 'OK' : 'MISMATCH') . "  readback " . ($ok_rd ? 'OK' : 'MISMATCH') . "\n";
exit($ok_ev && $ok_rd && $rc['status'] === '0x1' ? 0 : 2);
