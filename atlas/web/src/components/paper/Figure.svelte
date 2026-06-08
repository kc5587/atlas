<script lang="ts">
  import type { Snippet } from "svelte";

  let {
    n,
    caption,
    children,
  }: { n: number; caption: Snippet; children: Snippet } = $props();
  let el: HTMLElement;
  let shown = $state(false);

  $effect(() => {
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => entries.forEach((entry) => {
        if (entry.isIntersecting) shown = true;
      }),
      { threshold: 0.15 },
    );
    io.observe(el);
    return () => io.disconnect();
  });
</script>

<figure bind:this={el} class="reveal" class:in={shown}>
  {@render children()}
  <figcaption><span class="fl">Figure {n}.</span> {@render caption()}</figcaption>
</figure>

<style>
  figure {
    margin: 34px 0;
  }

  .reveal {
    opacity: 0;
    transform: translateY(14px);
    transition: opacity 0.7s ease, transform 0.7s cubic-bezier(0.2, 0.6, 0.3, 1);
  }

  .reveal.in {
    opacity: 1;
    transform: none;
  }

  figcaption {
    font-size: 15.5px;
    line-height: 1.45;
    color: var(--ink-soft);
    margin-top: 11px;
    max-width: 780px;
  }

  .fl {
    font-family: var(--mono);
    font-size: 12px;
    font-weight: 500;
    color: var(--ink);
  }
</style>
