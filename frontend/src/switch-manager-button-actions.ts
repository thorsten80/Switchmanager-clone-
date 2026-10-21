import { LitElement, html, css } from "lit";
import { customElement, property, query } from "lit/decorators.js";
import type { HomeAssistant, BlueprintButtonAction, SwitchConfigButtonAction } from "./types";

// Custom tab strip — replaces HA's legacy paper-tabs/paper-tab, which current HA
// no longer auto-loads. Plain buttons + CSS, so it never drifts with HA.
@customElement("switch-manager-button-actions")
export class SwitchManagerButtonActions extends LitElement {
  @property({ attribute: false }) hass!: HomeAssistant;
  @property({ attribute: false }) blueprint_actions?: BlueprintButtonAction[];
  @property({ attribute: false }) config_actions?: SwitchConfigButtonAction[];
  @property({ type: Number, reflect: true }) index = 0;
  @query(".tabs", true) tabs?: HTMLElement;

  render() {
    if (!this.blueprint_actions || this.blueprint_actions.length <= 1) {
      return html``;
    }

    return html`
      <div class="tabs" role="tablist">
        ${this.blueprint_actions.map((action, idx) => {
          const seqLen = this.config_actions?.[idx]?.sequence?.length || 0;
          return html`
            <button
              class="tab ${idx === this.index ? "selected" : ""}"
              role="tab"
              index="${idx}"
              @click=${() => this._select(idx)}
            >
              <span class="title">${action.title}</span>
              ${seqLen ? html`<span class="chip">${seqLen}</span>` : ""}
              ${action.title === "init"
                ? html`<ha-svg-icon
                    class="init-icon"
                    .path=${"M7,8L2.5,12L7,16V8M17,8V16L21.5,12L17,8M12,10A2,2 0 0,0 10,12A2,2 0 0,0 12,14A2,2 0 0,0 14,12A2,2 0 0,0 12,10Z"}
                  ></ha-svg-icon>`
                : ""}
            </button>
          `;
        })}
      </div>
    `;
  }

  flash(index: number) {
    const tab = this.tabs?.querySelector(`[index="${index}"]`) as HTMLElement;
    if (tab) {
      tab.removeAttribute("feedback");
      tab.setAttribute("feedback", "");
      setTimeout(() => tab.removeAttribute("feedback"), 1000);
    }
  }

  private _select(idx: number) {
    this.dispatchEvent(new CustomEvent("changed", { detail: { index: idx } }));
  }

  static styles = css`
    @keyframes feedback {
      to {
        border-color: #00e903;
        color: #00e903;
      }
    }
    :host {
      display: flex;
      justify-content: center;
    }
    .tabs {
      display: flex;
      justify-content: center;
      flex-wrap: wrap;
      gap: 4px;
      max-width: 100%;
      overflow-x: auto;
      margin: 0 10px;
    }
    .tab {
      position: relative;
      background: none;
      border: none;
      border-bottom: 2px solid transparent;
      color: var(--secondary-text-color);
      font: inherit;
      text-transform: uppercase;
      padding: 12px 32px;
      cursor: pointer;
      white-space: nowrap;
      display: inline-flex;
      align-items: center;
      gap: 8px;
    }
    .tab.selected {
      border-bottom-color: var(--primary-color);
      color: var(--primary-color);
    }
    .tab[feedback] {
      animation: 0.4s feedback;
      animation-iteration-count: 2;
      animation-direction: alternate;
    }
    .chip {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 20px;
      height: 20px;
      padding: 0 6px;
      border-radius: 10px;
      font-size: 12px;
      background: var(--primary-color);
      color: var(--text-primary-color, #fff);
    }
    .init-icon {
      --mdc-icon-size: 18px;
    }
  `;
}
