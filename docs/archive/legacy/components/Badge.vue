<template><span :class="['badge', level]">{{ label }}: {{ value }}</span></template>
<script setup>defineProps({label:String,value:[String,Number],level:String})</script>
<style scoped>.badge{padding:2px 6px;border-radius:6px;font-size:12px;margin:0 2px;}
.badge.good{color:#22c55e}.badge.fair{color:#eab308}.badge.poor{color:#ef4444}</style>