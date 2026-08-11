import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  onClose: () => void;
}

interface State {
  failed: boolean;
}

export class DetailErrorBoundary extends Component<Props, State> {
  state: State = { failed: false };

  static getDerivedStateFromError(): State {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("[ChronoChina detail-card render]", error, info);
  }

  render() {
    if (this.state.failed) {
      return (
        <article className="detail-card detail-card--error" role="alert">
          <button
            className="detail-card__close"
            type="button"
            onClick={this.props.onClose}
            aria-label="关闭详情"
          >×</button>
          <h2>该条记录的部分详情暂时无法显示</h2>
          <p>地图和时间轴仍可继续使用。</p>
        </article>
      );
    }
    return this.props.children;
  }
}
