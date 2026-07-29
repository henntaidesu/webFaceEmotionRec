<template>
  <div
    ref="deckEl"
    class="deck"
    :class="{ presenting }"
    @touchstart.passive="onTouchStart"
    @touchend.passive="onTouchEnd"
  >
    <!-- ── 顶栏 ── -->
    <header class="topbar">
      <span class="logo"><span class="pulse"></span>webFaceEmotionRec</span>

      <nav class="dots" :aria-label="ui.contents">
        <button
          v-for="(s, i) in slides"
          :key="i"
          class="dot"
          :class="{ on: i === index, past: i < index }"
          :title="s.title"
          @click="go(i)"
        ></button>
      </nav>

      <div class="tools">
        <RouterLink class="tbtn" :to="langTo">{{ locale.langSwitchLabel }}</RouterLink>
        <button class="tbtn" @click="overview = !overview">{{ overview ? ui.close : ui.contents }}</button>
        <button class="tbtn" @click="toggleFullscreen">{{ presenting ? ui.exitPresent : ui.present }}</button>
      </div>
    </header>

    <!-- ── 舞台（16:9 固定画布，等比缩放铺满） ── -->
    <div ref="stageEl" class="stage">
      <div class="canvas" :style="{ transform: `scale(${scale})` }">
        <Transition :name="dir > 0 ? 'sl-n' : 'sl-p'" mode="out-in">
          <section class="slide" :key="index">

            <div class="head">
              <div class="eyebrow"><span class="num">{{ cur.no }}</span><span class="lbl">{{ cur.eyebrow }}</span></div>
              <h2 class="sec-title">{{ cur.title }}</h2>
            </div>

            <div class="body">
              <!-- 01 研究背景 -->
              <template v-if="cur.kind === 'bg'">
                <p class="lead">{{ a.bgLead }}</p>
                <div class="rows">
                  <div class="row" v-for="(r, i) in a.bgRows" :key="i">
                    <span class="rk">{{ r.k }}</span>
                    <span class="rt"><b>{{ r.t }}</b><span class="sub">{{ r.sub }}</span></span>
                  </div>
                </div>
              </template>

              <!-- 02 研究目的 -->
              <template v-else-if="cur.kind === 'obj'">
                <div class="rqs">
                  <div class="rq" v-for="(q, i) in a.objRqs" :key="i">
                    <div class="rqn">{{ q.n }}</div><p>{{ q.p }}</p>
                  </div>
                </div>
                <div class="goal">{{ a.objGoal }}</div>
              </template>

              <!-- 03 先行研究 -->
              <template v-else-if="cur.kind === 'rel'">
                <div class="rows tight">
                  <div class="row" v-for="(r, i) in a.relRows" :key="i">
                    <span class="rk">{{ r.k }}</span>
                    <span class="rt"><b>{{ r.t }}</b><span class="sub">{{ r.sub }}</span></span>
                  </div>
                </div>
                <div class="goal">{{ a.relGap }}</div>
              </template>

              <!-- 04 研究方向 -->
              <template v-else-if="cur.kind === 'dir'">
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
              </template>

              <!-- 05 能解决什么问题 -->
              <template v-else-if="cur.kind === 'prob'">
                <p class="lead">{{ a.probLead }}</p>
                <div class="probs">
                  <div class="prob" v-for="(p, i) in a.probItems" :key="i">
                    <div class="pk">{{ p.k }}</div>
                    <p class="pain">{{ p.pain }}</p>
                    <p class="sol"><span class="arw">→</span>{{ p.sol }}</p>
                  </div>
                </div>
              </template>

              <!-- 06 预测的作用 -->
              <template v-else-if="cur.kind === 'why'">
                <p class="lead">{{ a.whyLead }}</p>
                <div class="tl">
                  <div class="tl-row" v-for="(r, i) in a.whyRows" :key="i" :class="{ good: i === 1 }">
                    <div class="tl-k">{{ r.k }}</div>
                    <div class="tl-steps">
                      <template v-for="(s, j) in r.steps" :key="j">
                        <span class="tl-step">{{ s }}</span>
                        <span v-if="j < r.steps.length - 1" class="tl-arw">→</span>
                      </template>
                    </div>
                    <div class="tl-v">{{ r.v }}</div>
                  </div>
                </div>
                <div class="io">
                  <div class="io-in">
                    <div class="iok">{{ a.actInLabel }}</div>
                    <div class="ioe mono">POST /api/predict</div>
                    <ul><li v-for="(x, i) in a.actOut" :key="i">{{ x }}</li></ul>
                  </div>
                  <span class="io-arw">→</span>
                  <div class="acts">
                    <div class="act" v-for="(w, i) in a.actItems" :key="i">
                      <div class="ak">{{ w.k }}</div>
                      <h3>{{ w.h }}</h3><p>{{ w.p }}</p>
                    </div>
                  </div>
                </div>
              </template>

              <!-- 07 现实应用 · 设计评审 -->
              <template v-else-if="cur.kind === 'dr'">
                <p class="lead">{{ a.drLead }}</p>
                <div class="case">
                  <div class="ctl">
                    <div class="cstep" v-for="(s, i) in a.drWalk" :key="i" :class="{ hit: s.hot }">
                      <span class="ct mono">{{ s.t }}</span>
                      <div class="cc"><b>{{ s.h }}</b><span>{{ s.p }}</span></div>
                    </div>
                  </div>
                  <div class="cright">
                    <div class="cmp bad">
                      <div class="cmp-h">{{ a.drNowTitle }}</div>
                      <p>{{ a.drNowText }}</p>
                    </div>
                    <div class="cmp good">
                      <div class="cmp-h">{{ a.drNewTitle }}</div>
                      <p>{{ a.drNewText }}</p>
                    </div>
                    <div class="solved">
                      <div class="solved-h">{{ a.drQLabel }}</div>
                      <ul><li v-for="(q, i) in a.drQs" :key="i">{{ q }}</li></ul>
                    </div>
                  </div>
                </div>
                <div class="more">
                  <span class="more-k">{{ a.appMoreLabel }}</span>
                  <span class="chip" v-for="(m, i) in a.appMore" :key="i">{{ m }}</span>
                </div>
                <p class="note">{{ a.drNote }}</p>
              </template>

              <!-- 08 走过的弯路 -->
              <template v-else-if="cur.kind === 'fail'">
                <p class="lead">{{ a.failLead }}</p>
                <div class="fails">
                  <div class="fail" v-for="(f, i) in a.failItems" :key="i">
                    <div class="fk"><span>{{ f.k }}</span><span class="fx">✕ {{ a.failTag }}</span></div>
                    <h3>{{ f.h }}</h3>
                    <div class="fline"><span class="fl">{{ a.failDidLabel }}</span><p>{{ f.did }}</p></div>
                    <div class="fline"><span class="fl">{{ a.failWhyLabel }}</span><p>{{ f.why }}</p></div>
                    <div class="fline lesson"><span class="fl">{{ a.failLessonLabel }}</span><p>{{ f.lesson }}</p></div>
                  </div>
                </div>
                <div class="goal">{{ a.failConclusion }}</div>
              </template>

              <!-- 09 当前进度 -->
              <template v-else-if="cur.kind === 'sta'">
                <div class="stats">
                  <div class="stat" v-for="(s, i) in a.staStats" :key="i">
                    <div class="sv mono">{{ s.v }}</div><div class="sl">{{ s.l }}</div>
                  </div>
                </div>
                <h3 class="mh">{{ a.staDoneLabel }} <span class="st">{{ a.staDoneTag }}</span></h3>
                <ul class="donelist">
                  <li v-for="(x, i) in a.staDone" :key="i">{{ x }}</li>
                </ul>
              </template>

              <!-- 10 计划进度 -->
              <template v-else-if="cur.kind === 'plan'">
                <p class="lead">{{ a.planLead }}</p>
                <div class="road">
                  <div class="phase" v-for="(p, i) in a.planPhases" :key="i" :class="{ next: i === 0 }">
                    <div class="pid">{{ p.id }}</div>
                    <div class="pwhen">{{ p.when }}</div>
                    <h3>{{ p.t }}</h3>
                    <ul><li v-for="(x, j) in p.items" :key="j">{{ x }}</li></ul>
                  </div>
                </div>
              </template>
            </div>
          </section>
        </Transition>
      </div>
    </div>

    <!-- ── 底栏 ── -->
    <footer class="botbar">
      <div class="bar"><span :style="{ width: `${(index / (slides.length - 1)) * 100}%` }"></span></div>
      <div class="ctrl">
        <button class="nav" :disabled="index === 0" @click="prev">‹ {{ ui.prev }}</button>
        <span class="counter mono">{{ String(index + 1).padStart(2, '0') }} / {{ String(slides.length).padStart(2, '0') }}</span>
        <button class="nav" :disabled="index === slides.length - 1" @click="next">{{ ui.next }} ›</button>
      </div>
    </footer>

    <!-- ── 目录 ── -->
    <div v-if="overview" class="ov" @click.self="overview = false">
      <div class="ov-inner">
        <div class="ov-head">{{ ui.contents }}</div>
        <div class="ov-grid">
          <button
            v-for="(s, i) in slides"
            :key="i"
            class="ov-card"
            :class="{ on: i === index }"
            @click="go(i); overview = false"
          >
            <span class="ov-no mono">{{ s.no || '—' }}</span>
            <span class="ov-t">{{ s.title || s.label }}</span>
            <span v-if="s.eyebrow" class="ov-e">{{ s.eyebrow }}</span>
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

const props = defineProps({
  locale: { type: Object, required: true },
})

const a = computed(() => props.locale.about)
const ui = computed(() => a.value.ui)

const route = useRoute()
const router = useRouter()

const slides = computed(() => {
  const t = a.value
  return [
    { kind: 'bg',   eyebrow: t.bgEyebrow,   title: t.bgTitle },
    { kind: 'obj',  eyebrow: t.objEyebrow,  title: t.objTitle },
    { kind: 'rel',  eyebrow: t.relEyebrow,  title: t.relTitle },
    { kind: 'dir',  eyebrow: t.dirEyebrow,  title: t.dirTitle },
    { kind: 'prob', eyebrow: t.probEyebrow, title: t.probTitle },
    { kind: 'why',  eyebrow: t.whyEyebrow,  title: t.whyTitle },
    { kind: 'dr',   eyebrow: t.drEyebrow,   title: t.drTitle },
    { kind: 'fail', eyebrow: t.failEyebrow, title: t.failTitle },
    { kind: 'sta',  eyebrow: t.staEyebrow,  title: t.staTitle },
    { kind: 'plan', eyebrow: t.planEyebrow, title: t.planTitle },
  ].map((s, i) => ({ ...s, no: String(i + 1).padStart(2, '0') }))
})

const clamp = (i) => Math.min(Math.max(i, 0), slides.value.length - 1)
const index = ref(clamp(Number(route.query.s || 1) - 1))
const dir = ref(1)
const overview = ref(false)
const cur = computed(() => slides.value[index.value])

// 切换语言时保留当前页
const langTo = computed(() => ({
  path: route.path.startsWith('/jp') ? '/cn/about' : '/jp/about',
  query: { s: index.value + 1 },
}))

function go(i) {
  const t = clamp(i)
  if (t === index.value) return
  dir.value = t > index.value ? 1 : -1
  index.value = t
}
const next = () => go(index.value + 1)
const prev = () => go(index.value - 1)

watch(index, (i) => {
  router.replace({ query: { ...route.query, s: i + 1 } }).catch(() => {})
})

// ── 16:9 画布等比缩放 ──
const SW = 1280
const SH = 720
const stageEl = ref(null)
const deckEl = ref(null)
const scale = ref(1)

function fit() {
  const el = stageEl.value
  if (!el) return
  scale.value = Math.min(el.clientWidth / SW, el.clientHeight / SH)
}

// ── 全屏演示 ──
const presenting = ref(false)

function toggleFullscreen() {
  if (document.fullscreenElement) document.exitFullscreen()
  else deckEl.value?.requestFullscreen?.().catch(() => {})
}

function onFsChange() {
  presenting.value = document.fullscreenElement === deckEl.value
  fit()
}

// ── 键盘 / 触摸 ──
function onKey(e) {
  if (e.altKey || e.ctrlKey || e.metaKey) return
  switch (e.key) {
    case 'ArrowRight': case 'ArrowDown': case 'PageDown': case ' ': case 'Enter':
      e.preventDefault(); next(); break
    case 'ArrowLeft': case 'ArrowUp': case 'PageUp': case 'Backspace':
      e.preventDefault(); prev(); break
    case 'Home': e.preventDefault(); go(0); break
    case 'End': e.preventDefault(); go(slides.value.length - 1); break
    case 'o': case 'O': overview.value = !overview.value; break
    case 'f': case 'F': toggleFullscreen(); break
    case 'Escape': overview.value = false; break
  }
}

let touchX = 0
const onTouchStart = (e) => { touchX = e.changedTouches[0].clientX }
function onTouchEnd(e) {
  const d = e.changedTouches[0].clientX - touchX
  if (Math.abs(d) > 60) (d < 0 ? next : prev)()
}

let ro
onMounted(() => {
  fit()
  ro = new ResizeObserver(fit)
  ro.observe(stageEl.value)
  window.addEventListener('keydown', onKey)
  document.addEventListener('fullscreenchange', onFsChange)
})
onUnmounted(() => {
  ro?.disconnect()
  window.removeEventListener('keydown', onKey)
  document.removeEventListener('fullscreenchange', onFsChange)
})
</script>

<style scoped>
.deck {
  --accent: #4fd1c5;
  --accent-dim: #2f8f86;
  --accent-soft: rgba(79, 209, 197, 0.1);
  --ember: #e0885c;
  --ember-soft: rgba(224, 136, 92, 0.1);
  position: relative;
  display: flex;
  flex-direction: column;
  flex: 1;
  min-height: 0;
  border: 1px solid var(--color-border);
  border-radius: 14px;
  overflow: hidden;
  background:
    radial-gradient(1100px 520px at 12% -10%, rgba(79, 209, 197, 0.07), transparent 60%),
    radial-gradient(900px 460px at 100% 110%, rgba(224, 136, 92, 0.06), transparent 60%),
    var(--color-bg);
  color: var(--color-text);
  line-height: 1.5;
}
.deck.presenting { border-radius: 0; border: none; }
.mono { font-family: ui-monospace, 'Cascadia Code', Consolas, monospace; font-variant-numeric: tabular-nums; }

/* ── 顶栏 ── */
.topbar {
  display: flex; align-items: center; gap: 16px;
  padding: 11px 16px; border-bottom: 1px solid var(--color-border);
  background: rgba(0, 0, 0, 0.35);
}
.logo {
  display: inline-flex; align-items: center; gap: 8px; flex: none;
  font-family: ui-monospace, Consolas, monospace; font-size: 12px; letter-spacing: 0.06em;
  color: var(--color-text-muted);
}
.pulse { width: 7px; height: 7px; border-radius: 50%; background: var(--accent); animation: pulse 2.4s infinite; flex: none; }
@keyframes pulse {
  0% { box-shadow: 0 0 0 0 var(--accent-soft); }
  70% { box-shadow: 0 0 0 8px transparent; }
  100% { box-shadow: 0 0 0 0 transparent; }
}
.dots { display: flex; align-items: center; gap: 6px; margin: 0 auto; flex-wrap: wrap; justify-content: center; }
.dot {
  width: 22px; height: 4px; border: none; border-radius: 2px; padding: 0;
  background: var(--color-border); cursor: pointer; transition: background 0.2s, transform 0.2s;
}
.dot:hover { transform: scaleY(1.8); }
.dot.past { background: var(--accent-dim); }
.dot.on { background: var(--accent); }
.tools { display: flex; gap: 7px; flex: none; }
.tbtn {
  padding: 5px 11px; border: 1px solid var(--color-border); border-radius: 20px;
  background: transparent; color: var(--color-text-muted);
  font-family: inherit; font-size: 12px; text-decoration: none; cursor: pointer;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}
.tbtn:hover { color: var(--accent); border-color: var(--accent-dim); background: var(--accent-soft); }

/* ── 舞台 / 画布 ── */
.stage { flex: 1; min-height: 0; display: grid; place-items: center; overflow: hidden; }
.canvas { width: 1280px; height: 720px; flex: none; transform-origin: center center; }
.slide { width: 100%; height: 100%; padding: 52px 64px; display: flex; flex-direction: column; justify-content: center; }

.sl-n-leave-active, .sl-p-leave-active { transition: opacity 0.12s ease, transform 0.12s ease; }
.sl-n-enter-active, .sl-p-enter-active { transition: opacity 0.26s ease, transform 0.3s cubic-bezier(0.22, 0.61, 0.36, 1); }
.sl-n-enter-from { opacity: 0; transform: translateX(44px); }
.sl-n-leave-to   { opacity: 0; transform: translateX(-28px); }
.sl-p-enter-from { opacity: 0; transform: translateX(-44px); }
.sl-p-leave-to   { opacity: 0; transform: translateX(28px); }

/* ── 内容页骨架 ── */
.head { flex: none; }
.eyebrow { display: flex; align-items: center; gap: 12px; font-size: 12px; letter-spacing: 0.13em; text-transform: uppercase; margin-bottom: 14px; }
.eyebrow .num {
  font-family: ui-monospace, Consolas, monospace; font-weight: 700; font-size: 12px;
  color: #08201e; background: var(--accent); border-radius: 5px; padding: 3px 8px; letter-spacing: 0.04em;
}
.eyebrow .lbl { color: var(--color-text-muted); font-weight: 600; }
.sec-title { font-size: 31px; font-weight: 720; line-height: 1.25; margin: 0; letter-spacing: -0.01em; text-wrap: balance; max-width: 940px; }
.body { flex: 0 1 auto; margin-top: 34px; display: flex; flex-direction: column; }
.lead { font-size: 15.5px; color: var(--color-text-muted); max-width: 1040px; margin: 0 0 20px; line-height: 1.6; }

/* ── 行列表 ── */
.rows { border-top: 1px solid var(--color-border); }
.row { display: grid; grid-template-columns: 96px 1fr; gap: 20px; padding: 15px 2px; border-bottom: 1px solid var(--color-border); align-items: baseline; }
.rows.tight .row { padding: 11px 2px; }
.rk { font-family: ui-monospace, Consolas, monospace; font-size: 12.5px; color: var(--accent); font-weight: 700; }
.rt { font-size: 15px; line-height: 1.5; }
.rt b { font-weight: 700; }
.rt .sub { display: block; color: var(--color-text-muted); font-size: 13.5px; margin-top: 3px; line-height: 1.5; }

/* ── 双线 ── */
.lanes { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.lane { border: 1px solid var(--color-border); border-radius: 14px; padding: 20px; background: var(--color-surface); }
.lane .tag { display: inline-block; font-family: ui-monospace, Consolas, monospace; font-size: 11px; letter-spacing: 0.06em; padding: 5px 10px; border-radius: 20px; border: 1px solid var(--color-border); color: var(--color-text-muted); margin-bottom: 13px; }
.lane.main { border-color: var(--accent-dim); }
.lane.main .tag { color: var(--accent); border-color: var(--accent-dim); }
.lane.side .tag { color: var(--ember); border-color: var(--ember); }
.lane h3 { margin: 0 0 5px; font-size: 18px; font-weight: 730; }
.lane .desc { font-size: 13.5px; color: var(--color-text-muted); line-height: 1.55; margin: 0 0 13px; }
.lane ul { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 8px; }
.lane li { font-size: 13px; line-height: 1.45; padding-left: 17px; position: relative; }
.lane li::before { content: ''; position: absolute; left: 0; top: 7px; width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }
.lane.side li::before { background: var(--ember); }
.shared { margin-top: 16px; text-align: center; font-size: 12.5px; color: var(--color-text-muted); line-height: 1.6; }

/* ── 研究问题 ── */
.rqs { display: grid; grid-template-columns: 1fr 1fr; gap: 13px; }
.rq { border: 1px solid var(--color-border); border-radius: 12px; padding: 16px 17px; background: var(--color-surface); }
.rq .rqn { font-family: ui-monospace, Consolas, monospace; font-weight: 700; font-size: 13px; color: var(--accent); letter-spacing: 0.04em; margin-bottom: 7px; }
.rq p { margin: 0; font-size: 14px; line-height: 1.5; }
.goal { margin-top: 16px; padding: 15px 18px; border-left: 3px solid var(--ember); background: var(--ember-soft); border-radius: 0 10px 10px 0; font-size: 14px; line-height: 1.55; }

/* ── 解决的问题 ── */
.probs { display: grid; grid-template-columns: 1fr 1fr; gap: 13px; }
.prob { position: relative; border: 1px solid var(--color-border); border-radius: 12px; padding: 15px 17px 14px; background: var(--color-surface); }
.prob .pk { font-family: ui-monospace, Consolas, monospace; font-size: 11px; font-weight: 700; color: var(--ember); letter-spacing: 0.06em; margin-bottom: 7px; }
.prob .pain { margin: 0 0 9px; font-size: 13px; line-height: 1.5; color: var(--color-text-muted); }
.prob .sol { margin: 0; font-size: 13.5px; line-height: 1.5; font-weight: 600; padding-top: 9px; border-top: 1px dashed var(--color-border); }
.prob .arw { color: var(--accent); font-weight: 700; margin-right: 7px; }

/* ── 为什么要预测 ── */
.tl { display: flex; flex-direction: column; gap: 9px; margin-bottom: 20px; }
.tl-row { display: grid; grid-template-columns: 92px 1fr 86px; gap: 14px; align-items: center; padding: 11px 14px; border: 1px solid var(--color-border); border-radius: 11px; background: var(--color-surface); }
.tl-row.good { border-color: var(--accent-dim); }
.tl-k { font-size: 12.5px; font-weight: 700; color: var(--color-text-muted); }
.tl-row.good .tl-k { color: var(--accent); }
.tl-steps { display: flex; align-items: center; gap: 9px; flex-wrap: wrap; }
.tl-step { font-size: 12.5px; padding: 5px 11px; border-radius: 20px; background: var(--color-surface-2); border: 1px solid var(--color-border); }
.tl-arw { color: var(--color-text-muted); font-size: 12px; }
.tl-v { font-family: ui-monospace, Consolas, monospace; font-size: 11.5px; font-weight: 700; text-align: center; padding: 4px 0; border-radius: 20px; color: var(--ember); background: var(--ember-soft); }
.tl-row.good .tl-v { color: var(--accent); background: var(--accent-soft); }

/* ── 具体例子 ── */
.case { display: grid; grid-template-columns: 1.15fr 1fr; gap: 18px; }
.ctl { position: relative; padding-left: 4px; }
.ctl::before { content: ''; position: absolute; left: 76px; top: 10px; bottom: 10px; width: 1px; background: var(--color-border); }
.cstep { display: grid; grid-template-columns: 72px 1fr; gap: 20px; padding: 7px 0; position: relative; }
.cstep::before { content: ''; position: absolute; left: 69px; top: 14px; width: 7px; height: 7px; border-radius: 50%; background: var(--color-border); border: 2px solid var(--color-bg); box-sizing: content-box; }
.cstep.hit::before { background: var(--ember); }
.ct { font-size: 11.5px; color: var(--color-text-muted); text-align: right; padding: 2px 12px 0 0; white-space: nowrap; }
.cstep.hit .ct { color: var(--ember); font-weight: 700; }
.cc b { display: block; font-size: 13px; font-weight: 700; line-height: 1.35; }
.cc span { display: block; font-size: 12px; color: var(--color-text-muted); line-height: 1.45; margin-top: 2px; }
.cright { display: flex; flex-direction: column; gap: 10px; }
.cmp { border: 1px solid var(--color-border); border-radius: 11px; padding: 11px 14px; background: var(--color-surface); }
.cmp-h { font-size: 12px; font-weight: 700; margin-bottom: 4px; }
.cmp p { margin: 0; font-size: 12px; line-height: 1.45; color: var(--color-text-muted); }
.cmp.bad { border-left: 3px solid var(--ember); }
.cmp.bad .cmp-h { color: var(--ember); }
.cmp.good { border-left: 3px solid var(--accent); }
.cmp.good .cmp-h { color: var(--accent); }
.solved { padding: 2px 2px 0; }
.solved-h { font-size: 12px; font-weight: 700; margin-bottom: 7px; }
.solved ul { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 6px; }
.solved li { font-size: 12px; line-height: 1.45; padding-left: 18px; position: relative; }
.solved li::before { content: '✓'; position: absolute; left: 0; color: var(--accent); font-weight: 700; }
.note { margin: 12px 0 0; font-size: 11.5px; color: var(--color-text-muted); opacity: 0.8; }
.more { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; margin-top: 15px; }
.more-k { font-size: 11.5px; color: var(--color-text-muted); }
.chip { font-size: 11.5px; padding: 4px 11px; border-radius: 20px; border: 1px solid var(--color-border); color: var(--color-text-muted); background: var(--color-surface); }

/* ── 失败尝试 ── */
.fails { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.fail { border: 1px solid var(--color-border); border-top: 2px solid var(--ember); border-radius: 2px 2px 12px 12px; padding: 15px 17px 14px; background: var(--color-surface); }
.fail .fk { display: flex; align-items: center; justify-content: space-between; font-family: ui-monospace, Consolas, monospace; font-size: 10.5px; letter-spacing: 0.06em; color: var(--color-text-muted); margin-bottom: 7px; }
.fail .fx { font-family: inherit; font-size: 11.5px; color: var(--ember); font-weight: 700; }
.fail h3 { margin: 0 0 11px; font-size: 15px; font-weight: 700; line-height: 1.3; }
.fline { display: grid; grid-template-columns: 62px 1fr; gap: 11px; padding: 7px 0; border-top: 1px solid var(--color-border); align-items: baseline; }
.fline .fl { font-size: 11px; color: var(--color-text-muted); letter-spacing: 0.04em; }
.fline p { margin: 0; font-size: 12.5px; line-height: 1.5; }
.fline.lesson .fl { color: var(--accent); }
.fline.lesson p { font-weight: 650; }

/* ── 预测之后的动作 ── */
.io { display: grid; grid-template-columns: 268px 20px 1fr; gap: 14px; align-items: center; }
.io-in { border: 1px solid var(--accent-dim); border-radius: 12px; padding: 15px 16px; background: var(--color-surface); }
.iok { font-size: 12px; color: var(--accent); font-weight: 700; margin-bottom: 8px; }
.ioe { font-size: 11.5px; color: var(--color-text-muted); padding: 4px 9px; border: 1px solid var(--color-border); border-radius: 6px; display: inline-block; margin-bottom: 11px; }
.io-in ul { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 7px; }
.io-in li { font-size: 12.5px; line-height: 1.45; padding-left: 15px; position: relative; }
.io-in li::before { content: ''; position: absolute; left: 0; top: 7px; width: 5px; height: 5px; border-radius: 50%; background: var(--accent); }
.io-arw { color: var(--accent); font-size: 19px; text-align: center; }
.acts { display: grid; grid-template-columns: repeat(3, 1fr); gap: 11px; }
.act { border: 1px solid var(--color-border); border-radius: 11px; padding: 13px 14px; background: var(--color-surface); }
.act .ak { font-family: ui-monospace, Consolas, monospace; font-size: 10px; letter-spacing: 0.06em; color: var(--ember); margin-bottom: 6px; }
.act h3 { margin: 0 0 5px; font-size: 13.5px; font-weight: 700; line-height: 1.3; }
.act p { margin: 0; font-size: 11.5px; line-height: 1.5; color: var(--color-text-muted); }

/* ── 当前进度 ── */
.stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 13px; margin-bottom: 26px; }
.stat { border: 1px solid var(--color-border); border-left: 3px solid var(--accent); border-radius: 0 11px 11px 0; padding: 14px 16px; background: var(--color-surface); }
.stat:last-child { border-left-color: var(--ember); }
.stat .sv { font-size: 21px; font-weight: 700; color: var(--accent); letter-spacing: -0.01em; }
.stat:last-child .sv { color: var(--ember); }
.stat .sl { font-size: 12.5px; color: var(--color-text-muted); margin-top: 5px; line-height: 1.45; }
.mh { margin: 0 0 13px; font-size: 15px; font-weight: 700; display: flex; align-items: center; gap: 9px; }
.mh .st { font-size: 11.5px; padding: 3px 10px; border-radius: 20px; font-weight: 600; color: var(--accent); background: var(--accent-soft); }
.donelist { margin: 0; padding: 0; list-style: none; display: grid; grid-template-columns: 1fr 1fr; gap: 10px 22px; }
.donelist li { font-size: 13.5px; line-height: 1.45; padding-left: 21px; position: relative; }
.donelist li::before { content: '✓'; position: absolute; left: 0; color: var(--accent); font-weight: 700; }

/* ── 路线图 ── */
.road { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; position: relative; }
.road::before { content: ''; position: absolute; left: 0; right: 0; top: 14px; height: 1px; background: var(--color-border); }
.phase { position: relative; border: 1px solid var(--color-border); border-radius: 12px; padding: 30px 15px 16px; background: var(--color-surface); }
.phase .pid {
  position: absolute; top: -1px; left: 15px; transform: translateY(-50%);
  font-family: ui-monospace, Consolas, monospace; font-size: 11.5px; font-weight: 700;
  color: var(--color-text-muted); background: var(--color-surface-2);
  border: 1px solid var(--color-border); border-radius: 20px; padding: 3px 10px;
}
.phase.next { border-color: var(--ember); }
.phase.next .pid { color: #1a0f08; background: var(--ember); border-color: var(--ember); }
.phase .pwhen { font-size: 11.5px; color: var(--color-text-muted); letter-spacing: 0.04em; margin-bottom: 4px; }
.phase.next .pwhen { color: var(--ember); }
.phase h3 { margin: 0 0 10px; font-size: 15px; font-weight: 700; line-height: 1.3; }
.phase ul { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 7px; }
.phase li { font-size: 12.5px; line-height: 1.45; color: var(--color-text-muted); padding-left: 14px; position: relative; }
.phase li::before { content: ''; position: absolute; left: 0; top: 7px; width: 5px; height: 5px; border-radius: 50%; background: var(--color-border); }
.phase.next li::before { background: var(--ember); }

/* ── 底栏 ── */
.botbar { flex: none; border-top: 1px solid var(--color-border); background: rgba(0, 0, 0, 0.35); }
.bar { height: 2px; background: var(--color-border); }
.bar span { display: block; height: 100%; background: var(--accent); transition: width 0.3s ease; }
.ctrl { display: flex; align-items: center; justify-content: center; gap: 20px; padding: 9px 16px; }
.nav {
  padding: 5px 14px; border: 1px solid var(--color-border); border-radius: 20px;
  background: transparent; color: var(--color-text-muted); font-family: inherit; font-size: 12.5px; cursor: pointer;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}
.nav:hover:not(:disabled) { color: var(--accent); border-color: var(--accent-dim); background: var(--accent-soft); }
.nav:disabled { opacity: 0.3; cursor: default; }
.counter { font-size: 12.5px; color: var(--color-text-muted); min-width: 74px; text-align: center; }

/* ── 目录 ── */
.ov { position: absolute; inset: 0; z-index: 5; background: rgba(0, 0, 0, 0.72); backdrop-filter: blur(6px); overflow-y: auto; padding: 28px; }
.ov-inner { max-width: 1000px; margin: 0 auto; }
.ov-head { font-family: ui-monospace, Consolas, monospace; font-size: 12px; letter-spacing: 0.14em; text-transform: uppercase; color: var(--color-text-muted); margin-bottom: 16px; }
.ov-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(210px, 1fr)); gap: 11px; }
.ov-card {
  display: flex; flex-direction: column; gap: 5px; text-align: left; cursor: pointer;
  padding: 13px 14px; border: 1px solid var(--color-border); border-radius: 11px;
  background: var(--color-surface); color: var(--color-text); font-family: inherit;
  transition: border-color 0.15s, background 0.15s, transform 0.15s;
}
.ov-card:hover { border-color: var(--accent-dim); background: var(--color-surface-2); transform: translateY(-2px); }
.ov-card.on { border-color: var(--accent); }
.ov-no { font-size: 11px; color: var(--accent); font-weight: 700; letter-spacing: 0.06em; }
.ov-t { font-size: 13.5px; font-weight: 650; line-height: 1.35; }
.ov-e { font-size: 11px; color: var(--color-text-muted); }

@media (prefers-reduced-motion: reduce) {
  .pulse { animation: none; }
  .sl-n-enter-active, .sl-p-enter-active, .sl-n-leave-active, .sl-p-leave-active { transition: none; }
}
</style>
