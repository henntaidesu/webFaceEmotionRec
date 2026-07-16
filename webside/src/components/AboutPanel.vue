<template>
  <div class="about">
    <!-- ── HERO ── -->
    <header class="hero">
      <span class="hero-tag">
        <span class="pulse"></span>AFFECTIVE COMPUTING · VR · {{ a.hero.tag }}
      </span>
      <h1 class="hero-title">{{ a.hero.title }}</h1>
      <p class="hero-sub">{{ a.hero.sub }}</p>
      <div class="hero-meta">
        <span>{{ a.hero.metaProjectLabel }} <b>webFaceEmotionRec</b></span>
        <span class="sep"></span>
        <span>{{ a.hero.presenterLabel }}<span class="mono">＿＿＿＿</span></span>
        <span class="sep"></span>
        <span class="mono">2026.07</span>
      </div>
    </header>

    <!-- ── 01 背景 ── -->
    <section class="sec">
      <div class="eyebrow"><span class="num">{{ a.bgNum }}</span><span class="lbl">{{ a.bgEyebrow }}</span></div>
      <h2 class="sec-title">{{ a.bgTitle }}</h2>
      <p class="lead">{{ a.bgLead }}</p>
      <div class="rows">
        <div class="row" v-for="(r, i) in a.bgRows" :key="i">
          <span class="rk">{{ r.k }}</span>
          <span class="rt"><b>{{ r.t }}</b><span class="sub">{{ r.sub }}</span></span>
        </div>
      </div>
    </section>

    <!-- ── 02 挑战与约束 ── -->
    <section class="sec">
      <div class="eyebrow"><span class="num">{{ a.conNum }}</span><span class="lbl">{{ a.conEyebrow }}</span></div>
      <h2 class="sec-title">{{ a.conTitle }}</h2>
      <div class="grid g4">
        <div class="card" v-for="(c, i) in a.conCards" :key="i">
          <div class="ck"><span class="dot"></span>{{ c.k }}</div>
          <h3>{{ c.h }}</h3><p>{{ c.p }}</p>
        </div>
      </div>
    </section>

    <!-- ── 03 研究方向总览 ── -->
    <section class="sec">
      <div class="eyebrow"><span class="num">{{ a.dirNum }}</span><span class="lbl">{{ a.dirEyebrow }}</span></div>
      <h2 class="sec-title">{{ a.dirTitle }}</h2>
      <div class="lanes">
        <div class="lane main">
          <span class="tag">{{ a.dirMainTag }}</span>
          <h3>{{ a.dirMainTitle }}</h3>
          <p class="desc">{{ a.dirMainDesc }}</p>
          <ul><li v-for="(x, i) in a.dirMainItems" :key="i">{{ x }}</li></ul>
        </div>
        <div class="lane side">
          <span class="tag">{{ a.dirSideTag }}</span>
          <h3>{{ a.dirSideTitle }}</h3>
          <p class="desc">{{ a.dirSideDesc }}</p>
          <ul><li v-for="(x, i) in a.dirSideItems" :key="i">{{ x }}</li></ul>
        </div>
      </div>
      <p class="shared">{{ a.dirShared }}</p>
    </section>

    <!-- ── 04 主线 ── -->
    <section class="sec">
      <div class="eyebrow"><span class="num">{{ a.mainNum }}</span><span class="lbl">{{ a.mainEyebrow }}</span></div>
      <h2 class="sec-title">{{ a.mainTitle }}</h2>
      <div class="flow">
        <template v-for="(n, i) in a.mainStages" :key="i">
          <div class="node"><div class="nk">{{ n.k }}</div><div class="nt">{{ n.t }}</div><div class="nd">{{ n.d }}</div></div>
          <span v-if="i < a.mainStages.length - 1" class="arrow">→</span>
        </template>
      </div>
      <div class="grid g3">
        <div class="card" v-for="(c, i) in a.mainBaselines" :key="i" :class="{ ember: i === 2 }">
          <div class="ck"><span class="dot"></span>{{ c.k }}</div>
          <h3>{{ c.h }}</h3><p>{{ c.p }}</p>
        </div>
      </div>
    </section>

    <!-- ── 05 支线 ── -->
    <section class="sec">
      <div class="eyebrow"><span class="num">{{ a.sideNum }}</span><span class="lbl">{{ a.sideEyebrow }}</span></div>
      <h2 class="sec-title">{{ a.sideTitle }}</h2>
      <div class="flow">
        <template v-for="(n, i) in a.sideNodes" :key="i">
          <div class="node"><div class="nk">{{ n.k }}</div><div class="nt">{{ n.t }}</div><div v-if="n.d" class="nd">{{ n.d }}</div></div>
          <span v-if="i < a.sideNodes.length - 1" class="arrow">→</span>
        </template>
      </div>
      <div class="loopnote">{{ a.sideLoop }}</div>
      <div class="grid g2">
        <div class="card" v-for="(c, i) in a.sideCards" :key="i" :class="{ ember: i === 1 }">
          <div class="ck"><span class="dot"></span>{{ c.k }}</div>
          <h3>{{ c.h }}</h3><p>{{ c.p }}</p>
        </div>
      </div>
    </section>

    <!-- ── 06 系统实现 ── -->
    <section class="sec">
      <div class="eyebrow"><span class="num">{{ a.sysNum }}</span><span class="lbl">{{ a.sysEyebrow }}</span></div>
      <h2 class="sec-title">{{ a.sysTitle }}</h2>
      <p class="lead">{{ a.sysLead }}</p>
      <div class="rows">
        <div class="row" v-for="(r, i) in a.sysRows" :key="i">
          <span class="rk">{{ r.k }}</span>
          <span class="rt"><b>{{ r.t }}</b><span class="sub">{{ r.sub }}</span></span>
        </div>
      </div>
    </section>

    <!-- ── 07 研究目的 ── -->
    <section class="sec">
      <div class="eyebrow"><span class="num">{{ a.objNum }}</span><span class="lbl">{{ a.objEyebrow }}</span></div>
      <h2 class="sec-title">{{ a.objTitle }}</h2>
      <div class="rqs">
        <div class="rq" v-for="(q, i) in a.objRqs" :key="i">
          <div class="rqn">{{ q.n }}</div><p>{{ q.p }}</p>
        </div>
      </div>
      <div class="goal">{{ a.objGoal }}</div>
    </section>

    <!-- ── 08 应用领域 ── -->
    <section class="sec">
      <div class="eyebrow"><span class="num">{{ a.appNum }}</span><span class="lbl">{{ a.appEyebrow }}</span></div>
      <h2 class="sec-title">{{ a.appTitle }}</h2>
      <div class="apps">
        <div class="app" v-for="(x, i) in a.appItems" :key="i">
          <span class="ai">{{ x.n }}</span>
          <div><h4>{{ x.h }}</h4><p>{{ x.p }}</p></div>
        </div>
      </div>
    </section>

    <!-- ── 09 进度与里程碑 ── -->
    <section class="sec">
      <div class="eyebrow"><span class="num">{{ a.staNum }}</span><span class="lbl">{{ a.staEyebrow }}</span></div>
      <h2 class="sec-title">{{ a.staTitle }}</h2>
      <div class="mile">
        <div class="mcol done">
          <h3>{{ a.staDoneLabel }} <span class="st">{{ a.staDoneTag }}</span></h3>
          <ul><li v-for="(x, i) in a.staDone" :key="i">{{ x }}</li></ul>
        </div>
        <div class="mcol todo">
          <h3>{{ a.staTodoLabel }} <span class="st">{{ a.staTodoTag }}</span></h3>
          <ul><li v-for="(x, i) in a.staTodo" :key="i">{{ x }}</li></ul>
        </div>
      </div>
    </section>

    <!-- ── 10 总结 ── -->
    <section class="sec summary">
      <div class="eyebrow"><span class="num">{{ a.sumNum }}</span><span class="lbl">{{ a.sumEyebrow }}</span></div>
      <h2 class="sec-title">{{ a.sumTitle }}</h2>
      <ul><li v-for="(x, i) in a.sumPoints" :key="i">{{ x }}</li></ul>
    </section>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  locale: { type: Object, required: true },
})

const a = computed(() => props.locale.about)
</script>

<style scoped>
.about {
  --accent: #4fd1c5;
  --accent-dim: #2f8f86;
  --accent-soft: rgba(79, 209, 197, 0.1);
  --ember: #e0885c;
  --ember-soft: rgba(224, 136, 92, 0.1);
  max-width: 1000px;
  margin: 0 auto;
  padding-bottom: 72px;
  color: var(--color-text);
  line-height: 1.5;
}
.mono {
  font-family: ui-monospace, 'Cascadia Code', Consolas, monospace;
  font-variant-numeric: tabular-nums;
}

/* ── hero ── */
.hero { padding: 8px 0 40px; border-bottom: 1px solid var(--color-border); }
.hero-tag {
  display: inline-flex; align-items: center; gap: 9px;
  font-family: ui-monospace, Consolas, monospace; font-size: 12px; letter-spacing: 0.1em;
  color: var(--accent); border: 1px solid var(--accent-dim); border-radius: 20px;
  padding: 6px 13px; margin-bottom: 24px;
}
.hero-tag .pulse {
  width: 8px; height: 8px; border-radius: 50%; background: var(--accent);
  animation: pulse 2.4s infinite;
}
@keyframes pulse {
  0% { box-shadow: 0 0 0 0 var(--accent-soft); }
  70% { box-shadow: 0 0 0 9px transparent; }
  100% { box-shadow: 0 0 0 0 transparent; }
}
.hero-title {
  font-size: clamp(26px, 3.4vw, 40px); line-height: 1.18; font-weight: 750;
  letter-spacing: -0.01em; margin: 0 0 16px; max-width: 20ch; text-wrap: balance;
}
.hero-sub { font-size: clamp(15px, 1.5vw, 18px); color: var(--color-text-muted); max-width: 52ch; margin: 0 0 28px; }
.hero-meta { display: flex; flex-wrap: wrap; gap: 8px 22px; align-items: center; font-size: 13.5px; color: var(--color-text-muted); }
.hero-meta b { color: var(--color-text); font-weight: 650; }
.hero-meta .mono { color: var(--color-text-muted); }
.hero-meta .sep { width: 1px; height: 13px; background: var(--color-border); }

/* ── section shell ── */
.sec { padding-top: 52px; }
.eyebrow { display: flex; align-items: center; gap: 12px; font-size: 12px; letter-spacing: 0.13em; text-transform: uppercase; margin-bottom: 18px; }
.eyebrow .num {
  font-family: ui-monospace, Consolas, monospace; font-weight: 700; font-size: 12px;
  color: #08201e; background: var(--accent); border-radius: 5px; padding: 3px 8px; letter-spacing: 0.04em;
}
.eyebrow .lbl { color: var(--color-text-muted); font-weight: 600; }
.sec-title { font-size: clamp(20px, 2.2vw, 28px); font-weight: 720; line-height: 1.25; margin: 0 0 14px; letter-spacing: -0.01em; text-wrap: balance; max-width: 24ch; }
.lead { font-size: 15.5px; color: var(--color-text-muted); max-width: 60ch; margin: 0; line-height: 1.6; }

/* ── rows ── */
.rows { margin-top: 26px; border-top: 1px solid var(--color-border); }
.row { display: grid; grid-template-columns: 56px 1fr; gap: 20px; padding: 16px 2px; border-bottom: 1px solid var(--color-border); align-items: baseline; }
.rk { font-family: ui-monospace, Consolas, monospace; font-size: 12.5px; color: var(--accent); font-weight: 700; }
.rt { font-size: 15px; line-height: 1.55; }
.rt b { font-weight: 700; }
.rt .sub { display: block; color: var(--color-text-muted); font-size: 13.5px; margin-top: 4px; line-height: 1.55; }

/* ── cards ── */
.grid { display: grid; gap: 14px; margin-top: 24px; }
.g2 { grid-template-columns: repeat(2, 1fr); }
.g3 { grid-template-columns: repeat(3, 1fr); }
.g4 { grid-template-columns: repeat(2, 1fr); }
.card { background: var(--color-surface); border: 1px solid var(--color-border); border-radius: var(--radius); padding: 18px 18px 16px; }
.card .ck { display: flex; align-items: center; gap: 8px; font-family: ui-monospace, Consolas, monospace; font-size: 11px; letter-spacing: 0.06em; color: var(--color-text-muted); margin-bottom: 10px; }
.card .ck .dot { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); flex: none; }
.card h3 { margin: 0 0 6px; font-size: 15.5px; font-weight: 700; line-height: 1.3; }
.card p { margin: 0; font-size: 13.5px; line-height: 1.55; color: var(--color-text-muted); }
.card.ember .ck .dot { background: var(--ember); }

/* ── lanes ── */
.lanes { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 24px; }
.lane { border: 1px solid var(--color-border); border-radius: 14px; padding: 20px; background: var(--color-surface); }
.lane .tag { display: inline-block; font-family: ui-monospace, Consolas, monospace; font-size: 11px; letter-spacing: 0.06em; padding: 5px 10px; border-radius: 20px; border: 1px solid var(--color-border); color: var(--color-text-muted); margin-bottom: 13px; }
.lane.main .tag { color: var(--accent); border-color: var(--accent-dim); }
.lane.side .tag { color: var(--ember); border-color: var(--ember); }
.lane h3 { margin: 0 0 5px; font-size: 17px; font-weight: 730; }
.lane .desc { font-size: 13.5px; color: var(--color-text-muted); line-height: 1.55; margin: 0 0 13px; }
.lane ul { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 8px; }
.lane li { font-size: 13px; line-height: 1.45; padding-left: 17px; position: relative; }
.lane li::before { content: ''; position: absolute; left: 0; top: 7px; width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }
.lane.side li::before { background: var(--ember); }
.shared { margin-top: 15px; text-align: center; font-size: 12.5px; color: var(--color-text-muted); line-height: 1.6; }

/* ── flow ── */
.flow { display: flex; flex-wrap: wrap; align-items: stretch; gap: 9px; margin-top: 24px; }
.node { flex: 1 1 0; min-width: 130px; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 11px; padding: 14px; }
.node .nk { font-family: ui-monospace, Consolas, monospace; font-size: 11px; letter-spacing: 0.05em; color: var(--accent); margin-bottom: 6px; }
.node .nt { font-size: 13.5px; font-weight: 650; line-height: 1.35; }
.node .nd { font-size: 12px; color: var(--color-text-muted); margin-top: 4px; line-height: 1.45; }
.arrow { align-self: center; color: var(--color-text-muted); font-size: 18px; flex: none; }
.loopnote { margin-top: 13px; font-family: ui-monospace, Consolas, monospace; font-size: 12px; color: var(--ember); display: flex; align-items: center; gap: 9px; }
.loopnote::before { content: ''; width: 24px; height: 1px; background: var(--ember); flex: none; }

/* ── objectives ── */
.rqs { display: grid; grid-template-columns: 1fr 1fr; gap: 13px; margin-top: 24px; }
.rq { border: 1px solid var(--color-border); border-radius: 12px; padding: 17px; background: var(--color-surface); }
.rq .rqn { font-family: ui-monospace, Consolas, monospace; font-weight: 700; font-size: 13px; color: var(--accent); letter-spacing: 0.04em; margin-bottom: 8px; }
.rq p { margin: 0; font-size: 14px; line-height: 1.5; }
.goal { margin-top: 16px; padding: 15px 18px; border-left: 3px solid var(--ember); background: var(--ember-soft); border-radius: 0 10px 10px 0; font-size: 14px; line-height: 1.55; }

/* ── apps ── */
.apps { display: grid; grid-template-columns: repeat(2, 1fr); gap: 13px; margin-top: 24px; }
.app { display: flex; gap: 13px; align-items: flex-start; padding: 14px 15px; border: 1px solid var(--color-border); border-radius: 11px; background: var(--color-surface); }
.app .ai { font-family: ui-monospace, Consolas, monospace; font-size: 12px; font-weight: 700; color: #08201e; background: var(--accent); border-radius: 6px; padding: 4px 8px; flex: none; margin-top: 1px; }
.app h4 { margin: 0 0 3px; font-size: 14.5px; font-weight: 700; }
.app p { margin: 0; font-size: 12.5px; color: var(--color-text-muted); line-height: 1.5; }

/* ── milestones ── */
.mile { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 24px; }
.mcol h3 { margin: 0 0 12px; font-size: 14.5px; display: flex; align-items: center; gap: 9px; font-weight: 700; }
.mcol h3 .st { font-family: ui-monospace, Consolas, monospace; font-size: 10.5px; padding: 3px 9px; border-radius: 20px; font-weight: 600; }
.mcol.done h3 .st { color: var(--accent); background: var(--accent-soft); }
.mcol.todo h3 .st { color: var(--ember); background: var(--ember-soft); }
.mcol ul { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 8px; }
.mcol li { font-size: 13px; line-height: 1.45; padding-left: 20px; position: relative; }
.mcol.done li::before { content: '✓'; position: absolute; left: 0; color: var(--accent); font-weight: 700; }
.mcol.todo li::before { content: '○'; position: absolute; left: 0; top: 1px; color: var(--ember); font-weight: 700; font-size: 11px; }

/* ── summary ── */
.summary ul { margin: 24px 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 14px; }
.summary li { font-size: 15px; line-height: 1.55; padding-left: 24px; position: relative; }
.summary li::before { content: ''; position: absolute; left: 0; top: 9px; width: 12px; height: 2px; background: var(--accent); }

@media (max-width: 760px) {
  .g2, .g3, .g4, .lanes, .rqs, .apps, .mile { grid-template-columns: 1fr; }
  .flow { flex-direction: column; }
  .arrow { transform: rotate(90deg); align-self: flex-start; margin-left: 20px; }
}
@media (prefers-reduced-motion: reduce) {
  .hero-tag .pulse { animation: none; }
}
</style>
