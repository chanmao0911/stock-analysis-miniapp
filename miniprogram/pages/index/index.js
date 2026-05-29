const { searchCompanies } = require("../../utils/api");

Page({
  data: {
    keyword: "",
    results: [],
    searching: false,
    hasSearched: false,
    error: "",
  },

  onInput(e) {
    this.setData({ keyword: e.detail.value });
  },

  onSearch() {
    const keyword = this.data.keyword.trim();
    if (!keyword) {
      this.setData({ error: "请输入公司名称" });
      return;
    }
    this._doSearch(keyword);
  },

  onQuickSearch(e) {
    const kw = e.currentTarget.dataset.kw;
    this.setData({ keyword: kw });
    this._doSearch(kw);
  },

  _doSearch(keyword) {
    this.setData({ searching: true, error: "", results: [] });

    searchCompanies(keyword)
      .then((res) => {
        if (res.code === 0 && res.data && res.data.length > 0) {
          this.setData({
            results: res.data,
            hasSearched: true,
            searching: false,
          });
        } else {
          this.setData({
            results: [],
            hasSearched: true,
            searching: false,
            error: res.message || "未找到匹配的公司",
          });
        }
      })
      .catch(() => {
        this.setData({
          searching: false,
          hasSearched: true,
          error: "网络请求失败，请检查后端服务是否启动",
        });
      });
  },

  onSelect(e) {
    const { code, name } = e.currentTarget.dataset;
    wx.navigateTo({
      url: `/pages/detail/detail?code=${code}&name=${name}`,
    });
  },
});
