package com.xun.xiaoju3;

import android.Manifest;
import android.os.Bundle;
import androidx.core.app.ActivityCompat;
import com.getcapacitor.BridgeActivity;
import android.webkit.WebView;
import android.webkit.WebViewClient;
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
        // WebView 渲染进程被杀（OOM/异常）绝不留死屏，立即加载本地兜底页
        //（crash.html：红底"重试/重启"按钮），点重试回 mobile.html
        if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.O) {
            WebView webView = (WebView) bridge.getWebView();
            webView.setWebViewClient(new WebViewClient() {
                @Override
                public boolean onRenderProcessGone(
                        WebView view,
                        android.webkit.RenderProcessGoneDetail detail) {
                    // 秘书审查修正：①RenderProcessGoneDetail=android.webkit
                    //   顶层类（非 WebViewClient 嵌套——嵌套写法=找不到符号）
                    // ②崩溃的 view 上 loadUrl 无效—— recreate() 整体重建
                    //   才是干净恢复（mobile.html 资产本地，重建即活）
                    // ③已知取舍：setWebViewClient 覆盖 Capacitor 桥 client
                    //   ——本地资产+fetch 架构下面极小，如实入档
                    recreate();
                    return true;   // 已接管，不再销毁 Activity
                }
            });
        }
    }
}
