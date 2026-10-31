package com.xun.xiaoju3;

import android.Manifest;
import android.os.Bundle;
import androidx.core.app.ActivityCompat;
import com.getcapacitor.Bridge;
import com.getcapacitor.BridgeActivity;
import com.getcapacitor.BridgeWebViewClient;
import android.webkit.RenderProcessGoneDetail;
import android.webkit.WebView;
import android.os.Build;

public class MainActivity extends BridgeActivity {
    @Override
    public void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        // 启动即请求运行时权限：相机（扫码配对）+ 麦克风（移动端语音转写，
        // WebView getUserMedia 需宿主持有授权后 onPermissionRequest 才会被放行）
        ActivityCompat.requestPermissions(this,
            new String[]{Manifest.permission.CAMERA,
                         Manifest.permission.RECORD_AUDIO}, 1001);
        // 红线加固 A3：渲染进程崩溃接管（2026-10-31 队长最高指令）——
        // WebView 渲染进程被杀（OOM/异常）绝不留死屏，recreate() 整体重建
        //（mobile.html 资产本地，重建即活）
        //
        // ★ P0 修复（2026-10-31 白屏事故）：本块曾用裸 WebViewClient 整体替换
        //   桥 client，把 BridgeWebViewClient.shouldInterceptRequest —— Capacitor
        //   本地资产拦截的唯一入口 —— 一并拆掉，http://localhost/ 直落网络栈
        //   → net::ERR_CONNECTION_REFUSED → 白屏（v2.3.1-cap 坏包根因）。
        //   现改为继承 BridgeWebViewClient 仅覆写 onRenderProcessGone，并经
        //   Bridge.setWebViewClient 正门装回（同步更新桥内部 webViewClient
        //   引用，本地资产拦截/外链跳转/onPageStarted 全链保留）。
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && bridge != null) {
            bridge.setWebViewClient(new RenderGoneClient(bridge, this));
        }
    }

    /**
     * 渲染进程崩溃接管 client。
     * 必须继承 BridgeWebViewClient：shouldInterceptRequest（本地资产服务）、
     * shouldOverrideUrlLoading（外链跳转）、onPageStarted（bridge.reset）全部
     * 继承保留，仅追加"渲染进程死亡→重建 Activity"一条语义。
     */
    private static class RenderGoneClient extends BridgeWebViewClient {
        private final MainActivity activity;

        RenderGoneClient(Bridge bridge, MainActivity activity) {
            super(bridge);
            this.activity = activity;
        }

        @Override
        public boolean onRenderProcessGone(WebView view, RenderProcessGoneDetail detail) {
            // 先走桥原逻辑（通知 WebView 监听者），保住继承链语义；
            // 崩溃的 view 上 loadUrl 无效——recreate() 整体重建才是干净恢复
            super.onRenderProcessGone(view, detail);
            activity.recreate();
            return true;   // 已接管，不再销毁 Activity
        }
    }
}
