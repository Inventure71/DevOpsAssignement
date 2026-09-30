import {createTransport, requestId} from "./transport.js";
import {createModel} from "./state.js";
import {createViews} from "./views.js";
import {createRenderer, createNotifier} from "./renderer.js";
import {createAudioController} from "./audio.js";
import {bindActions} from "./actions.js";
import {createRuntime} from "./runtime.js";

// Composition root: bind the browser, model, IO and presentation explicitly.
const app = document.querySelector("#app");
const leaveButton = document.querySelector("#leave-button");
const showNotice = createNotifier(document.querySelector("#notice"));
const model = createModel(localStorage);
const getState = () => model.ui.state;
const transport = createTransport(() => model.ui.roomId, getState);
let audio;
const markup = createViews(model.ui, () => audio.status, transport.now);
const {render, updateTimers} = createRenderer({app, leaveButton, document}, markup, transport.now, getState);
audio = createAudioController(transport, getState, transport.now, requestId(), model.readySent, render, showNotice);
const forgetRoom = () => { audio.reset(); model.forgetRoom(); render(); };
const runtime = createRuntime(model, transport, audio, render, showNotice, forgetRoom);
bindActions({app, leaveButton, navigator, confirm}, model, transport, audio, render, showNotice, forgetRoom);

document.addEventListener("visibilitychange", () => {
  if (!document.hidden) updateTimers();
});
window.addEventListener("pagehide", audio.stop);
setInterval(updateTimers, 100);
render();
runtime.start();
