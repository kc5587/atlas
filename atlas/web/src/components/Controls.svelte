<script lang="ts">
  let { stages = [] as string[], active = new Set<string>(), onToggle = (_: string) => {} }:
    { stages?: string[]; active?: Set<string>; onToggle?: (s: string) => void } = $props();
</script>

<div class="controls" role="group" aria-label="Stage filters">
  {#each stages as s (s)}
    <button
      type="button"
      class:on={active.has(s)}
      aria-pressed={active.has(s)}
      onclick={() => onToggle(s)}
    >{s}</button>
  {/each}
</div>

<style>
  .controls { position: absolute; bottom: 1rem; left: 1rem; z-index: 5; display: flex; gap: 0.4rem; }
  button {
    background: #1b2740; color: #cdd9e8; border: 1px solid #2c3e60; border-radius: 999px;
    padding: 0.3rem 0.8rem; cursor: pointer; text-transform: capitalize;
  }
  button.on { background: #2c4a78; color: #fff; }
</style>
