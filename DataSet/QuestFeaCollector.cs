// QuestFeaCollector.cs
// 自包含的 VR 数据采集（无需后端/网络）：
//   在头显里循环展示刺激图（360° 全景 skybox），同时把 Meta Quest Pro 的
//   63 维 FEA + 时间戳 + 当前图片名 记录到头显本地 CSV，用于训练模型。
//
// 前置：场景里有 OVRCameraRig，且 OVRManager 的 Face Tracking Support = Supported。
//
// 用法：
//   1) 把刺激图 jpg 放到 Assets/Resources/stimulus/ 下
//      （文件名建议 <emotion>_<序号>.jpg，如 happy_1.jpg，便于标注）。
//   2) 新建空物体挂本脚本（faceExpressions 留空会自动查找）。
//   3) Project Settings → Graphics → Always Included Shaders 里加入 "Skybox/Panoramic"
//      （确保打包不丢该 shader）。
//   4) Build & Run 到头显，戴上看图，自动记录。
//   5) 采集完取数据：
//      adb pull /sdcard/Android/data/<你的包名>/files/  ./capture_out
//      里面是 fea_session_*.csv。
//
// 记录列：timestamp_ms, image, 后接 63 个 OVRFaceExpressions（0~1）。

using System;
using System.Collections;
using System.IO;
using System.Text;
using UnityEngine;

public class QuestFeaCollector : MonoBehaviour
{
    [Header("引用（留空自动查找）")]
    public OVRFaceExpressions faceExpressions;

    [Header("采集参数")]
    [Tooltip("每张刺激图停留秒数")]
    public float dwellSeconds = 8f;
    [Tooltip("FEA 记录频率（帧/秒）")]
    public float logFps = 10f;
    [Tooltip("图片放完后是否循环")]
    public bool loop = true;

    private Texture2D[] _stimuli;
    private Material _skyboxMat;
    private StreamWriter _writer;
    private string _currentImage = "";
    private int _faceCount;

    private void Start()
    {
        if (faceExpressions == null)
            faceExpressions = FindObjectOfType<OVRFaceExpressions>();
        _faceCount = (int)OVRFaceExpressions.FaceExpression.Max; // 63

        // 载入 Assets/Resources/stimulus/ 下所有贴图
        _stimuli = Resources.LoadAll<Texture2D>("stimulus");
        Debug.Log($"[Collector] 载入刺激图 {(_stimuli == null ? 0 : _stimuli.Length)} 张");

        // 全景天空盒展示
        var sh = Shader.Find("Skybox/Panoramic");
        if (sh != null)
        {
            _skyboxMat = new Material(sh);
            RenderSettings.skybox = _skyboxMat;
        }
        else
        {
            Debug.LogWarning("[Collector] 找不到 Skybox/Panoramic shader，图片将不显示（记录仍正常）。");
        }

        // 打开 CSV
        string path = Path.Combine(Application.persistentDataPath,
            "fea_session_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".csv");
        _writer = new StreamWriter(path, false, Encoding.UTF8);
        var header = new StringBuilder("timestamp_ms,image");
        for (int i = 0; i < _faceCount; i++)
            header.Append(',').Append(((OVRFaceExpressions.FaceExpression)i).ToString());
        _writer.WriteLine(header.ToString());
        _writer.Flush();
        Debug.Log($"[Collector] 记录到 {path}（维度 {_faceCount}）");

        StartCoroutine(ShowLoop());
        StartCoroutine(LogLoop());
    }

    private IEnumerator ShowLoop()
    {
        if (_stimuli == null || _stimuli.Length == 0) yield break;
        var wait = new WaitForSeconds(Mathf.Max(1f, dwellSeconds));
        int idx = 0;
        while (true)
        {
            if (idx >= _stimuli.Length)
            {
                if (!loop) { Debug.Log("[Collector] 刺激序列播放完毕"); yield break; }
                idx = 0;
            }
            var tex = _stimuli[idx];
            _currentImage = tex.name;
            if (_skyboxMat != null) _skyboxMat.SetTexture("_MainTex", tex);
            idx++;
            yield return wait;
        }
    }

    private IEnumerator LogLoop()
    {
        var wait = new WaitForSeconds(1f / Mathf.Max(1f, logFps));
        while (true)
        {
            if (faceExpressions != null && faceExpressions.ValidExpressions && _writer != null)
            {
                var sb = new StringBuilder();
                sb.Append(DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()).Append(',').Append(_currentImage);
                for (int i = 0; i < _faceCount; i++)
                    sb.Append(',').Append(faceExpressions[(OVRFaceExpressions.FaceExpression)i].ToString("F4"));
                _writer.WriteLine(sb.ToString());
                _writer.Flush();
            }
            yield return wait;
        }
    }

    private void OnDestroy()
    {
        if (_writer != null) { _writer.Flush(); _writer.Close(); _writer = null; }
    }
}
