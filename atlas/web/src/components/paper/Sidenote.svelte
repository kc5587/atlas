<script lang="ts">
  import type { Snippet } from "svelte";

  let { n, children }: { n: number; children: Snippet } = $props();
</script>

<aside class="sidenote"><span class="sn">{n}.</span>{@render children()}</aside>

<style>
  .sidenote {
    font-family: var(--serif);
    font-size: 15px;
    line-height: 1.5;
    color: var(--ink-soft);
    border-left: 2px solid var(--rule-2);
    padding-left: 14px;
  }

  .sn {
    font-family: var(--mono);
    font-size: 11px;
    color: var(--blue);
    margin-right: 5px;
  }
</style>
