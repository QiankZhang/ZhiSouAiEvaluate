// 极简全局提示（pub-sub），用于删除/复制/编辑等操作后的成功或失败反馈。
// 用模块级订阅而非层层传 props，避免在很深的弹窗/表格行组件里也要接一条回调链。
let listeners = [];
let seq = 0;

export function subscribe(fn) {
  listeners.push(fn);
  return () => {
    listeners = listeners.filter((l) => l !== fn);
  };
}

function emit(message, tone) {
  const item = { id: ++seq, message, tone };
  listeners.forEach((fn) => fn(item));
}

export const toast = {
  success: (message) => emit(message, "success"),
  error: (message) => emit(message, "error"),
};
