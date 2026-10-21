// Lightweight overflow menu — replaces HA's legacy ha-button-menu/mwc-list-item,
// which current HA no longer auto-loads. Trigger uses ha-icon-button + ha-svg-icon
// (both reliably available); the surface and items are our own, so this never
// drifts with HA. Items are provided via the default slot as .menu-item elements.
import { LitElement, html, css } from "lit";
import { customElement, property, state } from "lit/decorators.js";

const mdiDotsVertical =
  "M12,16A2,2 0 0,1 14,18A2,2 0 0,1 12,20A2,2 0 0,1 10,18A2,2 0 0,1 12,16M12,10A2,2 0 0,1 14,12A2,2 0 0,1 12,14A2,2 0 0,1 10,12A2,2 0 0,1 12,10M12,4A2,2 0 0,1 14,6A2,2 0 0,1 12,8A2,2 0 0,1 10,6A2,2 0 0,1 12,4Z";

@customElement("switch-manager-menu")
export class SwitchManagerMenu extends LitElement {
  @property() path: string = mdiDotsVertical;
  @property() label = "Menu";
  /** "left" aligns the surface to the trigger's right edge (default), "right" to the left edge */
  @property() align: "left" | "right" = "left";
  @state() private _open = false;

  private _onDocClick = (e: MouseEvent) => {
    if (!e.composedPath().includes(this)) this._open = false;
  };

  connectedCallback() {
    super.connectedCallback();
    document.addEventListener("click", this._onDocClick);
  }
  disconnectedCallback() {
    super.disconnectedCallback();
    document.removeEventListener("click", this._onDocClick);
  }

  render() {
    return html`
      <ha-icon-button
        .path=${this.path}
        .label=${this.label}
        @click=${this._toggle}
      ></ha-icon-button>
      <div
        class="surface ${this.align}"
        ?hidden=${!this._open}
        @click=${this._onSurfaceClick}
      >
        <slot></slot>
      </div>
    `;
  }

  private _toggle(e: Event) {
    e.stopPropagation();
    this._open = !this._open;
  }

  private _onSurfaceClick(e: Event) {
    // Close after an item is chosen, unless the clicked item is disabled.
    const item = (e.target as HTMLElement).closest(".menu-item");
    if (item && item.hasAttribute("disabled")) {
      e.stopPropagation();
      return;
    }
    this._open = false;
  }

  static styles = css`
    :host {
      position: relative;
      display: inline-flex;
    }
    .surface {
      position: absolute;
      top: 100%;
      z-index: 9;
      min-width: 200px;
      padding: 8px 0;
      background: var(--card-background-color, var(--paper-card-background-color, #1c1c1c));
      border-radius: 8px;
      box-shadow: 0 5px 5px -3px rgba(0, 0, 0, 0.2),
        0 8px 10px 1px rgba(0, 0, 0, 0.14), 0 3px 14px 2px rgba(0, 0, 0, 0.12);
      color: var(--primary-text-color);
    }
    .surface.left {
      right: 0;
    }
    .surface.right {
      left: 0;
    }
    .surface[hidden] {
      display: none;
    }
    ::slotted(.menu-item) {
      display: flex;
      align-items: center;
      gap: 16px;
      padding: 0 16px;
      height: 48px;
      cursor: pointer;
      white-space: nowrap;
      box-sizing: border-box;
    }
    ::slotted(.menu-item:hover) {
      background: var(--secondary-background-color, rgba(255, 255, 255, 0.05));
    }
    ::slotted(.menu-item[disabled]) {
      opacity: 0.5;
      pointer-events: none;
    }
    ::slotted(.menu-divider) {
      height: 1px;
      margin: 8px 0;
      background: var(--divider-color, rgba(255, 255, 255, 0.12));
    }
    ::slotted(.menu-item.warning) {
      color: var(--error-color, #db4437);
    }
  `;
}
