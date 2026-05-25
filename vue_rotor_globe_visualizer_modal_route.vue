// File: src/components/RotorGlobe.vue
<template>
  <div class="relative w-full max-w-[720px] mx-auto">
    <!-- Title / Controls -->
    <div class="flex items-center justify-between mb-3">
      <div class="text-sm opacity-70">Bearing: <span class="font-semibold">{{ displayBearing }}</span> • Beamwidth: <span class="font-semibold">{{ beamwidth }}°</span></div>
      <div class="flex gap-2">
        <button class="px-3 py-1 rounded-xl bg-zinc-800 text-white shadow" @click="nudge(-5)" title="Left 5°">−5°</button>
        <button class="px-3 py-1 rounded-xl bg-zinc-800 text-white shadow" @click="nudge(5)" title="Right 5°">+5°</button>
      </div>
    </div>

    <!-- Globe canvas -->
    <svg :width="size" :height="size" :viewBox="`0 0 ${size} ${size}`" class="block select-none rounded-full shadow-2xl bg-gradient-to-b from-slate-900 to-slate-800 text-slate-200">
      <defs>
        <!-- Soft grid pattern for lat/long feel -->
        <pattern id="grid" width="20" height="20" patternUnits="userSpaceOnUse">
          <path d="M 20 0 L 0 0 0 20" class="stroke-white/10" fill="none"/>
        </pattern>
        <radialGradient id="vignette" cx="50%" cy="50%" r="50%">
          <stop offset="65%" stop-color="rgba(0,0,0,0)"/>
          <stop offset="100%" stop-color="rgba(0,0,0,0.35)"/>
        </radialGradient>
        <!-- Wedge gradient -->
        <linearGradient id="beam" x1="0%" y1="0%" x2="100%" y2="0%">
          <stop offset="0%" stop-color="#22d3ee" stop-opacity="0.3"/>
          <stop offset="100%" stop-color="#22d3ee" stop-opacity="0.05"/>
        </linearGradient>
      </defs>

      <!-- Globe base -->
      <g :transform="`translate(${center}, ${center})`">
        <circle :r="radius" fill="url(#grid)"/>
        <circle :r="radius" fill="url(#vignette)"/>

        <!-- Cardinal tick marks -->
        <g class="stroke-white/50">
          <template v-for="tick in ticks" :key="tick">
            <line :x1="0" :y1="-radius" :x2="0" :y2="-radius+ (tick % 30 === 0 ? 18 : 10)" :transform="`rotate(${tick})`" :stroke-width="tick % 30 === 0 ? 2 : 1" />
          </template>
        </g>

        <!-- Labels N E S W every 90° -->
        <g class="fill-white/80 text-[12px] font-semibold">
          <text :x="0" :y="-radius+34" text-anchor="middle">N</text>
          <text :x="radius-30" :y="5" text-anchor="end">E</text>
          <text :x="0" :y="radius-14" text-anchor="middle">S</text>
          <text :x="-radius+30" :y="5" text-anchor="start">W</text>
        </g>

        <!-- Beam wedge (animated by rotation) -->
        <g :style="rotStyle">
          <path :d="beamArcPath" fill="url(#beam)" class="transition-all duration-300"/>
          <line x1="0" y1="0" :x2="0" :y2="-radius" class="stroke-cyan-300" stroke-width="2"/>
        </g>

        <!-- Current bearing dot on rim -->
        <circle :cx="rimPoint.x" :cy="rimPoint.y" r="4" class="fill-cyan-300 drop-shadow" />
      </g>
    </svg>

    <!-- Footer status -->
    <div class="mt-3 text-xs text-slate-400 flex items-center justify-between">
      <div>
        <span class="inline-block w-2 h-2 rounded-full mr-2" :class="rotating ? 'bg-emerald-400 animate-pulse' : 'bg-slate-500'"></span>
        <span>{{ rotating ? 'Rotating…' : 'Idle' }}</span>
      </div>
      <div class="opacity-70">DIR {{ bearing.toFixed(0) }}°</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps({
  bearing: { type: Number, required: true }, // 0-359 CW from North
  beamwidth: { type: Number, default: 60 }, // total 3 dB BW, degrees
  size: { type: Number, default: 560 },
  rotating: { type: Boolean, default: false }
})

const center = computed(() => props.size / 2)
const radius = computed(() => props.size / 2 - 8)
const ticks = Array.from({ length: 360 }, (_, i) => i)

const displayBearing = computed(() => `${Math.round(((props.bearing % 360)+360)%360)}°`)

// Polar helpers
function toXY(angleDeg: number, r: number){
  const a = (angleDeg - 90) * Math.PI / 180 // 0° at North, clockwise
  return { x: Math.cos(a) * r, y: Math.sin(a) * r }
}

const half = computed(()=> props.beamwidth/2)

const beamArcPath = computed(() => {
  const r = radius.value
  const a0 = -half.value
  const a1 = half.value
  const p0 = toXY(a0, r)
  const p1 = toXY(a1, r)
  const large = props.beamwidth > 180 ? 1 : 0
  return [
    `M 0 0`,
    `L ${p0.x} ${p0.y}`,
    `A ${r} ${r} 0 ${large} 1 ${p1.x} ${p1.y}`,
    'Z'
  ].join(' ')
})

const rotStyle = computed(() => ({
  transform: `translate(${center.value}px, ${center.value}px) rotate(${props.bearing}deg)` ,
  transformOrigin: 'center center'
}))

const rimPoint = computed(() => toXY(0, radius.value))

const emit = defineEmits<{(e:'update:bearing', value:number):void}>()
function nudge(delta:number){
  emit('update:bearing', (((props.bearing + delta) % 360)+360)%360)
}
</script>

<style scoped>
svg { outline: none; }
.drop-shadow { filter: drop-shadow(0 0 6px rgba(34,211,238,0.6)); }
</style>


// File: src/components/RotorLink.vue
<template>
  <button @click="openPopup" class="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-800 text-white shadow hover:bg-slate-700">
    <span class="i-lucide-compass"></span>
    Open Rotor Globe
  </button>
</template>
<script setup lang="ts">
const props = defineProps<{ bearing:number, beamwidth?:number }>()
function openPopup(){
  const url = `/#/rotor-globe?bearing=${props.bearing}&beamwidth=${props.beamwidth ?? 60}`
  const w = 820, h = 860
  const y = window.top?.outerHeight ? Math.max(0, (window.top.outerHeight - h)/2) : 60
  const x = window.top?.outerWidth ? Math.max(0, (window.top.outerWidth - w)/2) : 60
  window.open(url, 'rotorGlobe', `width=${w},height=${h},left=${x},top=${y},resizable=yes,scrollbars=no`)
}
</script>


// File: src/views/RotorGlobeView.vue
<template>
  <div class="min-h-screen bg-slate-900 text-slate-100 p-6">
    <div class="max-w-5xl mx-auto">
      <div class="flex items-center justify-between mb-4">
        <h1 class="text-2xl font-bold">Rotor Globe</h1>
        <button @click="window.close()" class="px-3 py-1 rounded-xl bg-slate-800">Close</button>
      </div>
      <RotorGlobe v-model:bearing="bearing" :beamwidth="beamwidth" :rotating="rotating" :size="640"/>
    </div>
  </div>
</template>
<script setup lang="ts">
import { ref } from 'vue'
import RotorGlobe from '@/components/RotorGlobe.vue'

const params = new URLSearchParams(location.hash.split('?')[1] || '')
const bearing = ref(Number(params.get('bearing') ?? 0))
const beamwidth = ref(Number(params.get('beamwidth') ?? 60))
const rotating = ref(false)

// Optional: listen to postMessage from parent to live-update bearing
window.addEventListener('message', (ev)=>{
  if(ev?.data?.type === 'ROTATOR_UPDATE' && typeof ev.data.bearing === 'number'){
    bearing.value = ev.data.bearing
    rotating.value = !!ev.data.rotating
  }
})
</script>


// File: src/router/index.ts (excerpt)
// Add route
{
  path: '/rotor-globe',
  name: 'rotor-globe',
  component: () => import('@/views/RotorGlobeView.vue')
}


// File: src/types/rotor.d.ts
export type RotorStatus = { bearing:number; target?:number; moving:boolean }


// File: src/utils/rotorBridge.ts
export function sendRotorUpdateToPopup(win: Window | null, status: {bearing:number, moving:boolean}){
  if(!win) return
  win.postMessage({ type: 'ROTATOR_UPDATE', bearing: status.bearing, rotating: status.moving }, '*')
}


// File: USAGE (in your existing rotor page)
/*
<template>
  ...
  <RotorLink :bearing="radioDir" :beamwidth="yagiBW" />
</template>
<script setup lang="ts">
import RotorLink from '@/components/RotorLink.vue'
const radioDir = computed(()=> radioStatus.monitor /* or your live dir here */)
const yagiBW = 60
</script>
*/
