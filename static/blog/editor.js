document.addEventListener('DOMContentLoaded', () => {
  const tools = document.getElementById('writing-tools');
  if (!tools) return;
  const body = document.getElementById('id_body');
  const csrf = document.querySelector('[name=csrfmiddlewaretoken]').value;
  const status = document.getElementById('editor-status');
  async function send(url, data) {
    const response = await fetch(url, {method: 'POST', body: data, headers: {'X-CSRFToken': csrf}, credentials: 'same-origin'});
    if (!(response.headers.get('content-type') || '').includes('application/json')) throw new Error('登录已过期或请求被拒绝，请保存好文字后重新登录。');
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || '操作失败，请稍后重试。');
    return result;
  }
  document.getElementById('preview-markdown').addEventListener('click', async (event) => {
    const button = event.currentTarget;
    button.disabled = true;
    try {
      const data = new FormData(); data.append('body', body.value);
      const result = await send(tools.dataset.previewUrl, data);
      const preview = document.getElementById('markdown-preview');
      preview.innerHTML = result.html; // Server-rendered and sanitized by the same pipeline as public posts.
      preview.hidden = false; status.textContent = '预览已更新，文章尚未保存。';
    } catch (error) { status.textContent = error.message; }
    finally { button.disabled = false; }
  });
  document.getElementById('upload-photo')?.addEventListener('click', async (event) => {
    const input = document.getElementById('photo-file');
    if (!input.files[0]) { status.textContent = '请先选择图片。'; return; }
    if (input.files[0].size > 10 * 1024 * 1024) { status.textContent = '图片不能超过 10 MB。'; return; }
    const button = event.currentTarget; button.disabled = true; status.textContent = '正在上传并处理图片…';
    try {
      const data = new FormData(); data.append('image', input.files[0]); data.append('alt', document.getElementById('photo-alt').value);
      const result = await send(tools.dataset.uploadUrl, data);
      const alt = result.alt.replace(/[\\\[\]]/g, '\\$&').replace(/\r?\n/g, ' ');
      const insertion = '\n![' + alt + '](' + result.url + ')\n';
      body.setRangeText(insertion, body.selectionStart, body.selectionEnd, 'end');
      body.dispatchEvent(new Event('input', {bubbles: true}));
      const cover = document.getElementById('id_cover');
      cover.add(new Option(result.alt || result.id, result.id));
      status.textContent = '图片已上传并插入正文；请保存文章。也可以在封面下拉框中选择这张图片。';
      input.value = ''; body.focus();
    } catch (error) { status.textContent = error.message; }
    finally { button.disabled = false; }
  });
});
