export interface AgentStatus {
  id: number;
  name: string;
  role: string;
  energy: number;
  gold: number;
  food: number;
}

export class KingdomAgent {
  private token: string | null = null;
  private agentId: number | null = null;

  constructor(
    private baseUrl: string,
    private username: string,
    private password: string,
    private agentName: string,
    private role: string,
  ) {}

  private headers(): HeadersInit {
    if (!this.token) return { "Content-Type": "application/json" };
    return {
      "Content-Type": "application/json",
      Authorization: `Bearer ${this.token}`,
    };
  }

  private async post(path: string, payload: unknown): Promise<any> {
    const res = await fetch(`${this.baseUrl}${path}`, {
      method: "POST",
      headers: this.headers(),
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`);
    return res.json();
  }

  private async get(path: string): Promise<any> {
    const res = await fetch(`${this.baseUrl}${path}`, { headers: this.headers() });
    if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
    return res.json();
  }

  async registerUser(): Promise<void> {
    try {
      await this.post("/auth/register", { username: this.username, password: this.password });
    } catch {
      // ignore duplicate user registration
    }
  }

  async login(): Promise<void> {
    const body = await this.post("/auth/login", { username: this.username, password: this.password });
    this.token = body.data.token;
  }

  async registerAgent(): Promise<void> {
    const body = await this.post("/agent/register", { name: this.agentName, role: this.role });
    this.agentId = body.data.agent_id;
  }

  async autoRegister(): Promise<void> {
    await this.registerUser();
    await this.login();
    if (!this.agentId) {
      await this.registerAgent();
    }
  }

  async status(): Promise<AgentStatus> {
    if (!this.agentId) throw new Error("agentId not set");
    const body = await this.get(`/agent/status?agent_id=${this.agentId}`);
    return body.data as AgentStatus;
  }

  async work(task: string): Promise<any> {
    if (!this.agentId) throw new Error("agentId not set");
    const body = await this.post("/action/work", { agent_id: this.agentId, task });
    return body.data;
  }

  async train(troopType: "infantry" | "archer" | "cavalry", quantity: number): Promise<any> {
    if (!this.agentId) throw new Error("agentId not set");
    const body = await this.post("/action/train", {
      agent_id: this.agentId,
      troop_type: troopType,
      quantity,
    });
    return body.data;
  }
}
