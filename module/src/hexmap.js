/**
 * Foundry CLI Companion: hex-map toggles.
 *
 * Two buttons in the Tokens toolbar that show or hide, on your own screen only,
 * the hex labels and hex numbers that foundry-cli (`foundry hexmap`) draws on a
 * scene. Nothing is written to the world: other users are unaffected, and a
 * label's hide/reveal state (the eye) still decides what players can see.
 *
 * foundry-cli tags every Drawing it makes with flags.world.hexmap.kind:
 * "label", "number" or "anchor". Only labels and numbers get a toggle. This
 * contract is shared with hexstyle.py / foundry.py in the same repository.
 *
 * State is per page load: labels start hidden, numbers start shown.
 *
 * Keyboard: L toggles labels, N toggles numbers (rebindable under Configure
 * Controls). Neither key is used by Foundry core or the Shadowdark system.
 *
 * Why a refreshDrawing hook: a Drawing's visible shape lives in the primary
 * canvas group and Foundry resets its visibility on every redraw (document
 * updates, scene changes). Re-applying the toggle after each refresh is what
 * keeps a hidden label hidden.
 */

const MODULE_ID = "foundry-cli-companion";

const TOGGLES = {
    label: {title: "HEXMAP.ToggleLabels", icon: "fa-solid fa-tag", key: "KeyL"},
    number: {title: "HEXMAP.ToggleNumbers", icon: "fa-solid fa-hashtag", key: "KeyN"},
};

const shown = {label: false, number: true};

const kindOf = drawing => drawing.document.flags.world?.hexmap?.kind;

Hooks.on("refreshDrawing", drawing => {
    const kind = kindOf(drawing);
    if (!(kind in shown) || shown[kind]) return;
    drawing.visible = false;
    if (drawing.shape) drawing.shape.visible = false;
});

function refreshKind(kind) {
    if (!canvas.ready) return;
    for (const drawing of canvas.drawings.placeables) {
        if (kindOf(drawing) === kind) drawing.renderFlags.set({refreshVisibility: true});
    }
}

function setShown(kind, active) {
    shown[kind] = active;
    refreshKind(kind);
}

Hooks.once("init", () => {
    for (const [kind, {title, key}] of Object.entries(TOGGLES)) {
        game.keybindings.register(MODULE_ID, `toggle-${kind}`, {
            name: title,
            editable: [{key}],
            onDown: () => {
                setShown(kind, !shown[kind]);
                // Re-prepare the toolbar so its button shows the new state.
                ui.controls?.render({reset: true});
                return true;
            },
        });
    }
});

Hooks.on("getSceneControlButtons", controls => {
    if (!controls.tokens?.tools) return;
    for (const [kind, {title, icon}] of Object.entries(TOGGLES)) {
        const name = `hexmap-${kind}`;
        controls.tokens.tools[name] = {
            name,
            title,
            icon,
            order: Object.keys(controls.tokens.tools).length,
            toggle: true,
            active: shown[kind],
            onChange: (event, active) => setShown(kind, active),
        };
    }
});

// Fonts declared through CSS (such as the Shadowdark system's) are fetched
// lazily by the browser. Text drawn before its font arrives renders in a
// fallback font and doesn't redraw itself. Whenever a scene is drawn, load the
// fonts its hexmap drawings use, then redraw their text.
Hooks.on("canvasReady", async () => {
    const drawings = canvas.drawings.placeables.filter(kindOf);
    const fonts = new Set(drawings.map(d => d.document.fontFamily).filter(Boolean));
    if (!fonts.size) return;
    const results = await Promise.all([...fonts].map(f => document.fonts.load(`32px "${f}"`)));
    if (results.every(faces => !faces.length)) return;
    for (const drawing of drawings) {
        if (!drawing.destroyed) drawing.renderFlags.set({refreshText: true});
    }
});
