import { Entity, Script } from 'playcanvas';

/**
 * Cycles through a list of Gaussian splat scenes, each shown as a child entity of this script's
 * entity. A scene is either a single splat, referenced by the id of its `pc-asset`, or a flipbook
 * sequence (needs the gsplatFlipbook script asset to be loaded):
 *
 *     { "name": "Angel", "asset": "angel", "position": "0 1 0", "rotation": "0 -45 180", "scale": "1 1 1" }
 *     { "name": "Basketball", "rotation": "0 -90 180",
 *       "flipbook": { "folder": "https://...", "filenamePattern": "{frame:03}.compressed.ply",
 *                     "startFrame": 1, "endFrame": 149, "fps": 30, "playMode": "bounce" } }
 *
 * Switching:
 * - XR controllers: the secondary face button (gamepad button 5) - B on the right controller for
 *   the next scene, Y on the left for the previous one. Trigger, grip and thumbsticks belong to
 *   xrNavigation and xrMenu, and button 4 (X) toggles the xrMenu.
 * - Keyboard: N / P.
 * - App events `scene:next` / `scene:prev`, e.g. from xrMenu items for hand tracking.
 *
 * Fires `scene:changed` (index, scene) when a scene becomes visible.
 *
 * Declare the first scene's `pc-asset` normally so it preloads with the app, and the others `lazy`
 * so each loads the first time it's shown.
 */
export class SceneSwitcher extends Script {
    static scriptName = 'sceneSwitcher';

    /**
     * The scenes to cycle through.
     *
     * @attribute
     * @type {object[]}
     */
    scenes = [];

    /**
     * Index of the scene shown first.
     *
     * @attribute
     * @type {number}
     */
    startIndex = 0;

    /**
     * Gamepad button index that switches scenes (5 = B / Y on Meta Quest controllers).
     *
     * @attribute
     * @type {number}
     */
    buttonIndex = 5;

    /** @type {Entity|null} */
    _current = null;

    _index = 0;

    _token = 0;

    /** @type {Map<object, boolean>} */
    _wasPressed = new Map();

    initialize() {
        this._onNext = () => this.show(this._index + 1);
        this._onPrev = () => this.show(this._index - 1);
        this._onKeyDown = (e) => {
            if (e.repeat || e.ctrlKey || e.metaKey || e.altKey) return;
            if (e.key === 'n' || e.key === 'N') this._onNext();
            if (e.key === 'p' || e.key === 'P') this._onPrev();
        };

        this.app.on('scene:next', this._onNext);
        this.app.on('scene:prev', this._onPrev);
        window.addEventListener('keydown', this._onKeyDown);

        this.once('destroy', () => {
            this.app.off('scene:next', this._onNext);
            this.app.off('scene:prev', this._onPrev);
            window.removeEventListener('keydown', this._onKeyDown);
        });

        if (this.scenes.length) {
            this.show(this.startIndex);
        }
    }

    update() {
        const xr = this.app.xr;
        if (!xr?.active) return;

        for (const inputSource of xr.input.inputSources) {
            const button = inputSource.gamepad?.buttons?.[this.buttonIndex];
            const pressed = !!button?.pressed;
            if (pressed && !this._wasPressed.get(inputSource)) {
                if (inputSource.handedness === 'right') this._onNext();
                if (inputSource.handedness === 'left') this._onPrev();
            }
            this._wasPressed.set(inputSource, pressed);
        }
    }

    /**
     * Shows the scene at `index` (wrapping around), replacing the current one.
     *
     * @param {number} index - The scene index.
     */
    show(index) {
        const count = this.scenes.length;
        if (!count) return;

        this._index = ((index % count) + count) % count;
        const scene = this.scenes[this._index];
        const token = ++this._token;

        if (scene.flipbook) {
            this._replace(this._createEntity(scene));
            return;
        }

        const asset = this.app.assets.find(scene.asset, 'gsplat');
        if (!asset) {
            console.error(`sceneSwitcher: no gsplat pc-asset with id "${scene.asset}"`);
            return;
        }

        // Keep the current scene visible until the new splat has loaded
        const swap = () => {
            if (token !== this._token) return; // another switch happened meanwhile
            const entity = this._createEntity(scene);
            entity.gsplat.asset = asset;
            this._replace(entity);
        };
        if (asset.loaded) {
            swap();
        } else {
            asset.once('load', swap);
            this.app.assets.load(asset);
        }
    }

    _replace(entity) {
        // Destroying the old entity also destroys its flipbook script, which releases its frames
        this._current?.destroy();
        this._current = entity;
        this.entity.addChild(entity);
        this.app.fire('scene:changed', this._index, this.scenes[this._index]);
    }

    _createEntity(scene) {
        const entity = new Entity(scene.name ?? `scene-${this._index}`);
        if (scene.position) entity.setLocalPosition(...parseVec3(scene.position));
        if (scene.rotation) entity.setLocalEulerAngles(...parseVec3(scene.rotation));
        if (scene.scale) entity.setLocalScale(...parseVec3(scene.scale));
        entity.addComponent('gsplat', { castShadows: !!scene.castShadows });

        if (scene.flipbook) {
            entity.addComponent('script');
            entity.script.create('gsplatFlipbook', { properties: scene.flipbook });
        }
        return entity;
    }
}

function parseVec3(value) {
    return (Array.isArray(value) ? value : String(value).trim().split(/\s+/)).map(Number);
}
