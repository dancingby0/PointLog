<script setup>
import { onMounted } from "vue";
import AccountCard from "../components/AccountCard.vue";
import TxForm from "../components/TxForm.vue";
import TxList from "../components/TxList.vue";
import AssetSettleCard from "../components/AssetSettleCard.vue";
import AssetExportCard from "../components/AssetExportCard.vue";
import { refreshAssets } from "../store";

onMounted(() => refreshAssets());
</script>

<template>
  <div class="views">
    <h1 style="margin-bottom:12px">资产</h1>
    <AccountCard />
    <TxForm />
    <TxList />
    <AssetSettleCard />
    <AssetExportCard />
  </div>
</template>
