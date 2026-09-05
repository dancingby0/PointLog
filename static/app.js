// PointLog 前端：打卡记录（M1，Vue 3 实现）
const { createApp } = Vue;

createApp({
  data() {
    return {
      entries: [],           // 今日记录
      todayPoints: 0,        // 今日点数
      editingId: null,       // 正在编辑的记录 id；null 表示新增
      form: {                // 表单双向绑定的数据
        content: "",
        points: 1,
        category: "",
        ts: "",              // 本地时区的 YYYY-MM-DDTHH:mm
      },
    };
  },

  computed: {
    // 按时间从新到旧排列
    sortedEntries() {
      return [...this.entries].sort((a, b) => (a.ts < b.ts ? 1 : a.ts > b.ts ? -1 : 0));
    },
  },

  mounted() {
    this.loadEntries();
  },

  methods: {
    // 本地时区的 YYYY-MM-DDTHH:mm，用于 <input type=datetime-local>
    toLocalInput(d) {
      const p = (n) => String(n).padStart(2, "0");
      return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
    },

    // 把 ISO 时间格式化为可读显示
    formatTime(iso) {
      return new Date(iso).toLocaleString("zh-CN", { hour12: false });
    },

    async loadEntries() {
      try {
        const res = await fetch("/api/entries");
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "加载失败");
        this.entries = data.entries;
        this.todayPoints = data.today_points;
      } catch (err) {
        console.error(err);
        alert("加载失败：" + err.message);
      }
    },

    async submit() {
      const payload = {
        content: this.form.content.trim(),
        points: Number(this.form.points),
        category: this.form.category || null,
      };
      if (!payload.content) return;
      if (this.form.ts) {
        const dt = new Date(this.form.ts);
        if (!Number.isNaN(dt.getTime())) payload.ts = dt.toISOString();
      }

      const url = this.editingId ? `/api/entries/${this.editingId}` : "/api/entries";
      const method = this.editingId ? "PUT" : "POST";
      try {
        const res = await fetch(url, {
          method,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || (this.editingId ? "保存失败" : "提交失败"));
        this.endEdit();
        await this.loadEntries();
      } catch (err) {
        alert("提交失败：" + err.message);
      }
    },

    startEdit(entry) {
      this.editingId = entry.id;
      this.form.content = entry.content;
      this.form.points = entry.points;
      this.form.category = entry.category || "";
      this.form.ts = this.toLocalInput(new Date(entry.ts));
      window.scrollTo({ top: 0, behavior: "smooth" });
    },

    endEdit() {
      this.editingId = null;
      this.form.content = "";
      this.form.points = 1;
      this.form.category = "";
      this.form.ts = "";
    },

    async del(entry) {
      if (!confirm(`删除这条记录？\n${entry.content}`)) return;
      try {
        const res = await fetch(`/api/entries/${entry.id}`, { method: "DELETE" });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || "删除失败");
        await this.loadEntries();
      } catch (err) {
        alert("删除失败：" + err.message);
      }
    },
  },
}).mount("#app");