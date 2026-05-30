const app = getApp();

function request(path, params = {}) {
  return new Promise((resolve, reject) => {
    const baseUrl = app.globalData.apiBase;
    if (!baseUrl) {
      reject(new Error("未配置后端服务地址，请在 app.js 中设置 apiBase"));
      return;
    }
    const query = Object.keys(params)
      .map((k) => `${encodeURIComponent(k)}=${encodeURIComponent(params[k])}`)
      .join("&");
    const url = `${baseUrl}${path}${query ? "?" + query : ""}`;

    wx.request({
      url,
      method: "GET",
      timeout: 90000,
      success(res) {
        if (res.statusCode === 200) {
          resolve(res.data);
        } else {
          reject(new Error(`HTTP ${res.statusCode}`));
        }
      },
      fail(err) {
        reject(err);
      },
    });
  });
}

function searchCompanies(keyword) {
  return request("/api/search", { keyword });
}

function getCompanyData(stockCode) {
  return request(`/api/company/${stockCode}`);
}

module.exports = {
  searchCompanies,
  getCompanyData,
};
