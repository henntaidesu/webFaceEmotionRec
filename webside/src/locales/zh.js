export default {
  pageTitle: '人脸情感识别',
  langSwitchLabel: '日本語',
  langSwitchPath: '/jp',

  openCamera: '开启摄像头',
  closeCamera: '关闭摄像头',
  startDetection: '开始识别',
  stopDetection: '停止识别',
  modelLabel: '检测模型',
  fps: '帧率',

  statusError: '摄像头错误',
  statusConnecting: '连接中...',
  statusDetecting: '识别中',
  statusReady: '摄像头就绪',
  statusIdle: '未启动',

  noFaceTip: '未检测到人脸，请确认摄像头画面中有人脸',
  wsErrorMsg: '无法连接到后端服务，请确认后端已启动（http://localhost:9501）',
  cameraErrorPrefix: '无法访问摄像头：',
  cameraPlaceholderIcon: '📷',
  facePrefix: '人脸 #',

  emotionMap: {
    '愤怒': '愤怒',
    '厌恶': '厌恶',
    '恐惧': '恐惧',
    '开心': '开心',
    '悲伤': '悲伤',
    '惊讶': '惊讶',
    '平静': '平静',
  },

  detectorOptions: [
    { value: 'mtcnn',       label: 'MTCNN（默认）' },
    { value: 'retinaface',  label: 'RetinaFace（精度高）' },
    { value: 'opencv',      label: 'OpenCV Haar' },
    { value: 'ssd',         label: 'SSD' },
    { value: 'dlib',        label: 'Dlib HOG' },
    { value: 'mediapipe',   label: 'MediaPipe' },
    { value: 'yolov8',      label: 'YOLOv8' },
    { value: 'yunet',       label: 'YuNet' },
    { value: 'fastmtcnn',   label: 'Fast MTCNN' },
  ],
}
