<?php
namespace Demo;

class Bag implements \IteratorAggregate
{
    private array $items = [];
    public function getIterator(): \Generator { yield from $this->items; }
}
