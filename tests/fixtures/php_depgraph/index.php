<?php
require __DIR__ . '/src/Bag.php';
use Demo\Bag;
function main() { $b = new Bag(); return iterator_to_array($b); }
