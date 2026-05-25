<template>
  <div class="wrap">
    <svg ref="svgRef" :viewBox="`0 0 ${W} ${H}`" role="img" aria-label="World map"></svg>

    <div class="overlay">
      <div class="row"><span>Continent:</span><b>{{ continent }}</b></div>
      <div class="row"><span>CQ Zone:</span><b>{{ cqZone }}</b></div>
      <div class="row"><span>DXCC ID:</span><b>{{ dxccId }}</b></div>
      <div class="row"><span>Latitude:</span><b>{{ lat.toFixed(2) }}°</b></div>
      <div class="row"><span>Longitude:</span><b>{{ lon.toFixed(2) }}°</b></div>
      <div class="row" v-if="grid"><span>Grid:</span><b>{{ grid }}</b></div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { geoNaturalEarth1, geoPath } from 'd3-geo'
import * as topojson from 'topojson-client'
import topo from '@/assets/countries-110m.json' // local TopoJSON

const props = defineProps({
  countryName: { type: String, required: true },
  continent:   { type: String, required: true },
  cqZone:      { type: [String, Number], required: true },
  dxccId:      { type: [String, Number], required: true },
  lat:         { type: Number, required: true },
  lon:         { type: Number, required: true },
  dxLat:       { type: Number, default: null },
  dxLon:       { type: Number, default: null },
  grid:        { type: String, default: '' }
})

const W = 960, H = 520
const svgRef = ref(null)

function draw(){
  const svg = svgRef.value
  svg.innerHTML = ''

  // Convert to GeoJSON
  const countriesGeo = topojson.feature(topo, topo.objects.countries)
  const proj = geoNaturalEarth1().fitSize([W, H], { type: 'Sphere' })
  const path = geoPath(proj)

  // Background
  const defs = add(svg, 'defs')
  const ocean = add(defs, 'radialGradient', { id: 'ocean' })
  add(ocean, 'stop', { offset: '0%', 'stop-color': '#1f2a37' })
  add(ocean, 'stop', { offset: '100%', 'stop-color': '#0b1220' })
  add(svg, 'path', { d: path({ type: 'Sphere' }), fill: 'url(#ocean)' })

  const g = add(svg, 'g')
  const norm = s => s?.toLowerCase().normalize('NFKD').replace(/\p{Diacritic}/gu,'').replace(/[\u0300-\u036f]/g,'')
  const target = norm(props.countryName)

  for(const f of countriesGeo.features){
    const name = norm(f.properties?.name || f.properties?.NAME || f.properties?.ADMIN)
    const p = add(g, 'path', { d: path(f), fill:'#2b3443', stroke:'#5f6b7a', 'stroke-width':0.4 })
    if (name && (name===target || name.includes(target))){
      p.setAttribute('fill', '#3b82f6')
      p.setAttribute('stroke', '#93c5fd')
      p.setAttribute('stroke-width', 0.8)
    }
  }

  // Station marker
  const [sx, sy] = proj([props.lon, props.lat])
  circle(svg, sx, sy, 3.2, '#fff')
  circle(svg, sx, sy, 7, 'none', 'rgba(255,255,255,.5)')

  // Optional DX line
  if (props.dxLat != null && props.dxLon != null){
    const arc = { type:'LineString', coordinates:[[props.lon, props.lat],[props.dxLon, props.dxLat]] }
    add(svg, 'path', { d:path(arc), fill:'none', stroke:'#9ca3af', 'stroke-dasharray':'4 3', 'stroke-width':1 })
  }
}

function add(parent, tag, attrs={}){
  const n = document.createElementNS('http://www.w3.org/2000/svg', tag)
  for(const [k,v] of Object.entries(attrs)) n.setAttribute(k,v)
  parent.appendChild(n)
  return n
}
function circle(svg, x, y, r, fill='none', stroke='none'){
  const a = { cx:x, cy:y, r }
  if (fill!=='none') a.fill = fill
  if (stroke!=='none') a.stroke = stroke
  add(svg, 'circle', a)
}

onMounted(draw)
watch(() => [props.countryName, props.lat, props.lon, props.dxLat, props.dxLon], draw)
</script>

<style scoped>
.wrap{ position: relative; width: 100%; height: calc(100% - 56px); }
svg{ width:100%; height:100%; display:block; background:#0b1220; }
.overlay{
  position:absolute; top:12px; left:12px;
  background:rgba(0,0,0,.55); border:1px solid rgba(255,255,255,.08);
  padding:10px 12px; border-radius:10px; color:#e9eef5; font-size:14px;
}
.row{ display:flex; gap:.5rem; margin:.15rem 0; white-space:nowrap; }
.row span{ opacity:.8; }
.row b{ font-weight:600; }
</style>
