<script setup>
import TagPoolManager from "../components/TagPoolManager.vue";
</script>

<template>
  <div class="views">
    <h1 style="margin-bottom:12px">设置</h1>

    <TagPoolManager
      scope="diary"
      title="日记标签池（当前档案）"
      hint="用于打卡类别；随档案隔离"
    />
    <TagPoolManager
      scope="asset"
      title="资产标签池（个人）"
      hint="用于收支/平台标签；全局共享"
    />
  </div>
</template>
