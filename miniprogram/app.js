App({
  onLaunch() {
    console.log("上市公司股票分析 小程序启动");
  },
  globalData: {
    // Base URL of the backend API
    // Change this to your actual server address in production
    apiBase: "http://192.168.31.79:8000",
  },
});
