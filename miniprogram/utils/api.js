const app = getApp();

/**
 * Send request to the backend API.
 */
function request(path, params = {}) {
  return new Promise((resolve, reject) => {
    // In dev mode, use localhost. For phone testing, change to LAN IP.
    const baseUrl = app.globalData.apiBase || 'http://192.168.31.79:8000';
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

/**
 * Search for companies by name keyword.
 */
function searchCompanies(keyword) {
  return request("/api/search", { keyword });
}

/**
 * Get all financial data for a company.
 */
function getCompanyData(stockCode) {
  return request(`/api/company/${stockCode}`);
}

module.exports = {
  searchCompanies,
  getCompanyData,
};
