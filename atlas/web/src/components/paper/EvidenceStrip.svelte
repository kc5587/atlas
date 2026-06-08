<script lang="ts">
  import type { Signal } from "../../lib/signals";

  let { signal }: { signal: Signal } = $props();
</script>

<div class="strip">
  {#each signal.evidence_chain as step, i}
    <div class="cell">
      <div class="stage">{step.stage}</div>
      <div class="val num">{step.value}</div>
      <div class="metric">{step.metric}</div>
    </div>
    {#if i < signal.evidence_chain.length - 1}<div class="arrow">→</div>{/if}
  {/each}
</div>

<style>
  .strip {
    display: flex;
    align-items: center;
    gap: 10px;
    flex-wrap: wrap;
    margin: 14px 0;
  }

  .cell {
    border: 1px solid var(--rule-2);
    padding: 8px 12px;
    min-width: 120px;
  }

  .stage {
    font-family: var(--mono);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: var(--muted);
  }

  .val {
    font-size: 20px;
    color: var(--ink);
  }

  .metric {
    font-size: 12px;
    color: var(--ink-soft);
    font-style: italic;
  }

  .arrow {
    color: var(--rule-2);
    font-family: var(--mono);
  }
</style>
