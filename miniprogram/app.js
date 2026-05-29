App({
  onLaunch() {
    console.log("查财报 小程序启动");
  },
  globalData: {
    // 云托管部署后，填入云托管服务的外网访问地址
    // 格式如: https://xxx.ap-shanghai.run.tcloudbase.com
    // 开发调试时可改为本地地址: http://localhost:8000
    apiBase: "",
  },
});
