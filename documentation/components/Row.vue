<template>
<div class='flex justify-between'>
  <span>{{ band }}</span>
  <span>Day: {{ day || '—' }} / Night: {{ night || '—' }}</span>
</div>
</template>
<script setup>defineProps({band:String,day:String,night:String})</script>
