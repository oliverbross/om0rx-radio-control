<template>
  <div v-if="open" class="backdrop" @click.self="$emit('close')">
    <div class="modal">
      <header class="bar">
        <h3>Additional Information</h3>
        <button class="x" @click="$emit('close')">✕</button>
      </header>

      <!-- Choose ONE: SVG (d3-geo) or Leaflet -->
      <WorldAtlasLocal
        v-if="engine==='svg'"
        :countryName="countryName"
        :continent="continent"
        :cqZone="cqZone"
        :dxccId="dxccId"
        :lat="lat" :lon="lon"
        :dxLat="dxLat" :dxLon="dxLon"
        :grid="grid"
      />
      <LeafletCountryModal
        v-else
        :countryName="countryName"
        :continent="continent"
        :cqZone="cqZone"
        :dxccId="dxccId"
        :lat="lat" :lon="lon"
        :grid="grid"
      />
    </div>
  </div>
</template>

<script setup>
import WorldAtlasLocal from './WorldAtlasLocal.vue'
import LeafletCountryModal from './LeafletCountryModal.vue'

defineProps({
  open: { type: Boolean, default: false },
  engine: { type: String, default: 'svg' }, // 'svg' or 'leaflet'
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
</script>

<style scoped>
.backdrop{ position:fixed; inset:0; background:rgba(0,0,0,.55); display:grid; place-items:center; z-index:1000; }
.modal{ width:min(980px,95vw); height:min(600px,92vh); background:#1e1f25; border-radius:14px; box-shadow:0 12px 40px rgba(0,0,0,.5); overflow:hidden; position:relative; }
.bar{ height:56px; display:flex; align-items:center; justify-content:space-between; padding:0 16px; border-bottom:1px solid rgba(255,255,255,.08); color:#9cc2ff; }
.bar h3{ margin:0; font-size:20px; font-weight:700; }
.x{ width:34px; height:34px; border-radius:50%; background:rgba(0,0,0,.5); color:#fff; border:1px solid rgba(255,255,255,.1); cursor:pointer; }
</style>
