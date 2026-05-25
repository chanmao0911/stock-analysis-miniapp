const { getCompanyData } = require("../../utils/api");

Page({
  data: {
    stockCode: "",
    loading: true,
    error: "",

    // Pre-computed display data
    name: "",
    full_name: "",
    market: "",
    industry: "",
    profile: "",
    business_scope: "",
    today_open: null,
    today_date: "",

    revenue_structure: [],
    years: ["2021", "2022", "2023", "2024", "2025", "2026(最新)"],

    // Each metric: { label, unit, source, values: [...] }
    revenue_rows: [],
    eps_rows: [],
    high_rows: [],
    low_rows: [],
    nav_rows: [],
    alr_rows: [],

    // Shareholders
    sh_rows: [],
    sh_max: "",
    sh_min: "",
    sh_current: "",

    sources: {},
  },

  onLoad(options) {
    const { code, name } = options;
    if (!code) {
      this.setData({ error: "缺少股票代码参数", loading: false });
      return;
    }
    wx.setNavigationBarTitle({ title: name || "公司详情" });
    this.setData({ stockCode: code });
    this.fetchData(code);
  },

  fetchData(code) {
    const that = this;
    that.setData({ loading: true, error: "" });

    getCompanyData(code)
      .then(function (res) {
        if (res.code === 0 && res.data) {
          that.buildDisplayData(res.data);
        } else {
          that.setData({
            error: res.message || "未查询到该公司数据",
            loading: false,
          });
        }
      })
      .catch(function () {
        that.setData({
          error: "网络请求失败，请确认后端服务已启动，手机和电脑在同一WiFi",
          loading: false,
        });
      });
  },

  buildDisplayData(d) {
    var that = this;
    var yearKeys = [2021, 2022, 2023, 2024, 2025, 2026];

    function fmt(v) {
      if (v === null || v === undefined || v === "") return "-";
      var n = Number(v);
      if (isNaN(n)) return "-";
      return n.toFixed(2);
    }

    function fmtCount(v) {
      if (v === null || v === undefined || v === "") return "-";
      var n = Number(v);
      if (isNaN(n)) return "-";
      if (n >= 10000) return (n / 10000).toFixed(2) + "万";
      return String(n);
    }

    // Build row data for each metric
    function makeRows(dataObj) {
      var arr = [];
      for (var i = 0; i < yearKeys.length; i++) {
        var v = dataObj ? dataObj[yearKeys[i]] : null;
        arr.push(v !== undefined && v !== null ? fmt(v) : "-");
      }
      return arr;
    }

    function makeRowsRaw(dataObj) {
      var arr = [];
      for (var i = 0; i < yearKeys.length; i++) {
        var v = dataObj ? dataObj[yearKeys[i]] : null;
        arr.push(v !== undefined && v !== null ? v : "-");
      }
      return arr;
    }

    var sources = d.sources || {};

    // Pre-compute all display arrays
    var updateData = {
      loading: false,
      name: d.name || d.full_name || "",
      full_name: d.full_name || d.name || "",
      market: d.market || "",
      industry: d.industry || "",
      profile: d.profile || "",
      business_scope: d.business_scope || "",
      today_open: d.today_open || null,
      today_date: d.today_date || "",
      revenue_structure: d.revenue_structure || [],

      // Revenue
      revenue_rows: makeRows(d.revenue),
      // EPS
      eps_rows: makeRows(d.eps),
      // Stock price high/low
      high_rows: makeRows(d.stock_price_high),
      low_rows: makeRows(d.stock_price_low),
      // Net assets per share
      nav_rows: makeRows(d.net_assets_per_share),
      // Asset-liability ratio
      alr_rows: makeRowsRaw(d.asset_liability_ratio),
    };

    // Shareholders
    var sh = d.shareholders || {};
    var shByYear = sh.by_year || {};
    var shArr = [];
    for (var j = 0; j < yearKeys.length; j++) {
      var sv = shByYear[yearKeys[j]];
      shArr.push(sv !== undefined && sv !== null ? fmtCount(sv) : "-");
    }

    updateData.sh_rows = shArr;
    updateData.sh_max = fmtCount(sh.max_count);
    if (sh.max_count_year) updateData.sh_max += " (" + sh.max_count_year + "年)";
    updateData.sh_min = fmtCount(sh.min_count);
    if (sh.min_count_year) updateData.sh_min += " (" + sh.min_count_year + "年)";
    updateData.sh_current = fmtCount(sh.current_count);

    that.setData(updateData);
  },

  goBack() {
    wx.navigateBack();
  },
});
