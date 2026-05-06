export default {
  pageTitle: '顔感情認識',
  langSwitchLabel: '中文',
  langSwitchPath: '/cn',

  openCamera: 'カメラを起動',
  closeCamera: 'カメラを停止',
  startDetection: '認識開始',
  stopDetection: '認識停止',
  modelLabel: '検出モデル',
  fps: 'フレームレート',

  statusError: 'カメラエラー',
  statusConnecting: '接続中...',
  statusDetecting: '認識中',
  statusReady: 'カメラ準備完了',
  statusIdle: '未起動',

  noFaceTip: '顔が検出されていません。カメラに顔が映っているか確認してください',
  wsErrorMsg: 'バックエンドサービスに接続できません。バックエンドが起動しているか確認してください（http://localhost:9501）',
  cameraErrorPrefix: 'カメラにアクセスできません：',
  cameraPlaceholderIcon: '📷',
  facePrefix: '顔 #',

  emotionMap: {
    '愤怒': '怒り',
    '厌恶': '嫌悪',
    '恐惧': '恐怖',
    '开心': '喜び',
    '悲伤': '悲しみ',
    '惊讶': '驚き',
    '平静': '平静',
  },

  detectorOptions: [
    { value: 'mtcnn',       label: 'MTCNN（デフォルト）' },
    { value: 'retinaface',  label: 'RetinaFace（高精度）' },
    { value: 'opencv',      label: 'OpenCV Haar' },
    { value: 'ssd',         label: 'SSD' },
    { value: 'dlib',        label: 'Dlib HOG' },
    { value: 'mediapipe',   label: 'MediaPipe' },
    { value: 'yolov8',      label: 'YOLOv8' },
    { value: 'yunet',       label: 'YuNet' },
    { value: 'fastmtcnn',   label: 'Fast MTCNN' },
  ],
}
