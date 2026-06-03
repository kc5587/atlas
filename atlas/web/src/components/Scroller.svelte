<script lang="ts">
  import { onMount } from "svelte";
  import scrollama from "scrollama";
  import { SCENES } from "../lib/scenes";
  import { activeScene, mode } from "../stores";

  let container: HTMLDivElement;
  let current = $state(0);

  function applyScene(index: number) {
    activeScene.set(index);
    mode.set(SCENES[index].id === "explore" ? "explore" : "story");
  }

  onMount(() => {
    const scroller = scrollama();
    scroller
      .setup({ step: ".scene-step", offset: 0.5 })
      .onStepEnter(({ index }) => {
        current = index;
        applyScene(index);
      })
      .onStepExit(({ index, direction }) => {
        // when leaving the first step upward, fall back to the whole-graph scene
        if (index === 0 && direction === "up") {
          current = 0;
          applyScene(0);
        }
      });
    const onResize = () => scroller.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      scroller.destroy();
    };
  });

  function goto(index: number) {
    const clamped = Math.max(0, Math.min(SCENES.length - 1, index));
    const el = container?.querySelectorAll<HTMLElement>(".scene-step")[clamped];
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    el?.focus({ preventScroll: true });
  }
</script>

<div bind:this={container} class="scroller">
  {#each SCENES as s, i (s.id)}
    <section
      class="scene-step"
      class:active={i === current}
      tabindex="0"
      role="group"
      aria-roledescription="scene"
      aria-label={`Scene ${i + 1} of ${SCENES.length}: ${s.title}`}
      aria-current={i === current ? "true" : undefined}
    >
      <h2>{s.title}</h2>
      <p>{s.body}</p>
      <nav class="scene-nav" aria-label="Scene navigation">
        <button type="button" onclick={() => goto(i - 1)} disabled={i === 0} aria-label="Previous scene">
          ← Prev
        </button>
        <span class="scene-count">{i + 1} / {SCENES.length}</span>
        <button
          type="button"
          onclick={() => goto(i + 1)}
          disabled={i === SCENES.length - 1}
          aria-label="Next scene"
        >
          Next →
        </button>
      </nav>
    </section>
  {/each}
</div>

<style>
  .scroller { position: relative; z-index: 2; width: min(420px, 90vw); margin-left: 2rem; }
  .scene-step {
    min-height: 90vh; display: flex; flex-direction: column; justify-content: center;
    color: #e8eef6; padding: 1.5rem; background: rgba(13, 20, 34, 0.72);
    border-radius: 12px; margin: 18vh 0; outline: none;
    transition: box-shadow 0.2s ease, opacity 0.2s ease; opacity: 0.7;
  }
  .scene-step.active { opacity: 1; box-shadow: 0 0 0 1px #2c4a78, 0 8px 30px rgba(0, 0, 0, 0.4); }
  .scene-step:focus-visible { box-shadow: 0 0 0 2px #5c8bd6; }
  h2 { font-size: 1.6rem; margin: 0 0 0.5rem; }
  p { font-size: 1.05rem; line-height: 1.5; opacity: 0.9; }
  .scene-nav { display: flex; align-items: center; gap: 0.6rem; margin-top: 1.2rem; }
  .scene-nav button {
    background: #1b2740; color: #cdd9e8; border: 1px solid #2c3e60; border-radius: 999px;
    padding: 0.3rem 0.8rem; cursor: pointer; font-size: 0.85rem;
  }
  .scene-nav button:disabled { opacity: 0.4; cursor: default; }
  .scene-count { font-size: 0.8rem; opacity: 0.7; }
</style>
