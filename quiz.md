# Quiz — Amazon EKS (Elastic Kubernetes Service)

Five questions. Answers are collapsed below each question — try them first.

---

## 1. An AZ goes down. What happens to the EKS control plane?

A. The cluster is unavailable until the AZ recovers
B. Nothing user-visible — the control plane is replicated across 3 AZs and keeps serving
C. Worker nodes take over the API server
D. The cluster automatically migrates to another region

<details>
<summary>Answer</summary>

**B.** AWS runs the control plane (API server, etcd, scheduler) across
multiple AZs with an SLA of 99.95%. An AZ outage may take out some of your
worker nodes — that's what Pod Disruption Budgets and multi-AZ node groups
are for — but the API server itself stays up.

</details>

---

## 2. A pod needs to read a specific S3 bucket. What is the least-privilege way?

A. Attach an S3 policy to the worker node's IAM role
B. Bake AWS credentials into the container image
C. IRSA — give the pod's ServiceAccount its own IAM role via the cluster OIDC provider
D. Put the bucket name in an environment variable

<details>
<summary>Answer</summary>

**C.** IRSA (IAM Roles for Service Accounts) lets each pod assume its own
scoped role. Option A gives *every* pod on that node the same S3 access —
one compromised pod leaks the whole node's permissions. B is never acceptable.

</details>

---

## 3. Traffic spikes and pending pods wait 4 minutes for new nodes. What fixes this best?

A. Add more static nodes to the node group
B. Karpenter — it provisions right-sized nodes in seconds, picking the cheapest instance that fits the pending pod
C. Increase the pod's CPU requests
D. Enable the Cluster Autoscaler with a higher max

<details>
<summary>Answer</summary>

**B.** Karpenter reacts to unschedulable pods directly and launches exactly
the instance type the pod needs, usually in under a minute. The classic
Cluster Autoscaler works from node-group templates, so it is slower and can
only scale in fixed instance shapes.

</details>

---

## 4. You are upgrading from Kubernetes 1.31 to 1.32. What is the correct order?

A. Nodes first, then the control plane
B. Control plane → managed add-ons → worker nodes
C. Everything at once with one eksctl command
D. Add-ons first, then control plane, then nodes

<details>
<summary>Answer</summary>

**B.** The control plane leads, add-ons follow (VPC CNI, CoreDNS, kube-proxy
must match the new version), and nodes go last — one minor version at a time.
Upgrading nodes first leaves them talking to an older API server that may
not understand their kubelet version.

</details>

---

## 5. Your worker nodes sit in public subnets with public IPs. What is the risk?

A. None — the security group blocks inbound traffic anyway
B. Pods become reachable from the internet, nodes are directly exposed, and a misconfigured security group turns into a breach
C. It only costs more — NAT Gateway is cheaper than public IPs
D. EKS refuses to run nodes in public subnets

<details>
<summary>Answer</summary>

**B.** Nodes in public subnets with public IPs are directly internet-addressable.
Best practice is private subnets only, with the ALB in public subnets as the
single entry point and NAT Gateways for outbound-only internet access (image
pulls, patching). Defence in depth beats a single security group rule.

</details>
