<template>
  <div class="map" ref="mapEl"></div>
  <div class="overlay">
    <div class="row"><span>Continent:</span><b>{{ continent }}</b></div>
    <div class="row"><span>CQ Zone:</span><b>{{ cqZone }}</b></div>
    <div class="row"><span>DXCC ID:</span><b>{{ dxccId }}</b></div>
    <div class="row"><span>Latitude:</span><b>{{ lat.toFixed(2) }}°</b></div>
    <div class="row"><span>Longitude:</span><b>{{ lon.toFixed(2) }}°</b></div>
    <div class="row" v-if="grid"><span>Grid:</span><b>{{ grid }}</b></div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import * as topojson from 'topojson-client'
import topo from '@/assets/countries-110m.json'

const props = defineProps({
  countryName: { type: String, required: true },
  continent:   { type: String, required: true },
  cqZone:      { type: [String, Number], required: true },
  dxccId:      { type: [String, Number], required: true },
  lat:         { type: Number, required: true },
  lon:         { type: Number, required: true },
  grid:        { type: String, default: '' }
})

const mapEl = ref(null)
let map, layer, marker

function draw(){
  if(!map){
    map = L.map(mapEl.value, { zoomControl:false, attributionControl:false })
  }
  if(layer){ layer.remove(); layer=null }
  if(marker){ marker.remove(); marker=null }

  const countriesGeo = topojson.feature(topo, topo.objects.countries)
  const features = countriesGeo.features
  const norm = s => s?.toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g,'')
  const target = norm(props.countryName)

  const f = features.find(ff => {
    const n = norm(ff.properties?.name || ff.properties?.NAME || ff.properties?.ADMIN)
    return n && (n===target || n.includes(target))
  })

  if(f){
    layer = L.geoJSON(f, {
      style: { weight: 1.5, fillOpacity:.25 }
    }).addTo(map)
    map.fitBounds(layer.getBounds().pad(0.15))
  }else{
    map.setView([props.lat, props.lon], 3)
  }

  marker = L.marker([props.lat, props.lon]).addTo(map)
}

onMounted(draw)
onBeforeUnmount(() => map && map.remove())
watch(() => [props.countryName, props.lat, props.lon], draw)
</script>

<style scoped>
.map{ position:absolute; inset:56px 0 0 0; } /* below header in modal */
.overlay{
  position:absolute; top:68px; left:12px;
  background:rgba(0,0,0,.55); border:1px solid rgba(255,255,255,.08);
  padding:10px 12px; border-radius:10px; color:#e9eef5; font-size:14px;
}
.row{ display:flex; gap:.5rem; margin:.15rem 0; white-space:nowrap; }
.row span{ opacity:.8; } .row b{ font-weight:600; }
</style>
