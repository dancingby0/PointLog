<script setup>
// ECharts 通用包装组件（按需引入，控制打包体积）：传入 option 即渲染。
// 用法：<EChart :option="lineOption" style="height:280px" />
import * as echarts from "echarts/core";
import { BarChart, LineChart, PieChart } from "echarts/charts";
import {
  GridComponent,
  LegendComponent,
  TooltipComponent,
} from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";

echarts.use([
  BarChart,
  LineChart,
  PieChart,
  GridComponent,
  LegendComponent,
  TooltipComponent,
  CanvasRenderer,
]);

const props = defineProps({
  option: { type: Object, required: true },
});

const el = ref(null);
let chart = null;

function render() {
  if (!chart && el.value) {
    chart = echarts.init(el.value);
  }
  if (chart && props.option) {
    chart.setOption(props.option, true);
  }
}

function onResize() {
  chart && chart.resize();
}

onMounted(() => {
  render();
  window.addEventListener("resize", onResize);
});

watch(() => props.option, render, { deep: true });

onBeforeUnmount(() => {
  window.removeEventListener("resize", onResize);
  chart && chart.dispose();
  chart = null;
});
</script>

<template>
  <div ref="el" class="echart"></div>
</template>

<style scoped>
.echart { width: 100%; height: 100%; }
</style>
