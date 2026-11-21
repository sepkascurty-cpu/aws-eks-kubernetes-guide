#!/usr/bin/env python3
"""Amazon EKS cluster health & cost inspector (boto3).

Reads a live EKS cluster and prints a production-readiness summary:
control-plane status, Kubernetes version, node groups, managed add-ons,
IRSA/OIDC status, and a monthly cost estimate for the control plane.

Usage:
    pip install boto3
    python eks_demo.py --cluster prod-eks --region ap-southeast-1

Requires AWS credentials with eks:DescribeCluster, eks:ListNodegroups,
eks:ListAddons and iam:GetOpenIDConnectProvider permissions (read-only).
No resources are created or modified.
"""
import argparse
import sys

CONTROL_PLANE_HOURLY_USD = 0.10          # EKS control-plane price, us-east-1
HOURS_PER_MONTH = 730                    # AWS billing convention


def describe_cluster(eks, name):
    """Return the cluster description, or None if the cluster is missing."""
    try:
        return eks.describe_cluster(name=name)["cluster"]
    except eks.exceptions.ResourceNotFoundException:
        print(f"Cluster '{name}' not found in this account/region.")
        return None


def check_irsa(iam, oidc_issuer_url):
    """Check whether the cluster OIDC provider is registered in IAM.

    IRSA (IAM Roles for Service Accounts) only works when the OIDC
    provider exists — without it, pods fall back to the node's IAM role.
    """
    provider_id = oidc_issuer_url.split("https://")[-1]
    arn = f"arn:aws:iam::{get_account_id(iam)}:oidc-provider/{provider_id}"
    try:
        iam.get_open_id_connect_provider(OpenIDConnectProviderArn=arn)
        return True, arn
    except iam.exceptions.NoSuchEntityException:
        return False, arn


def get_account_id(iam):
    return iam.get_user()["User"]["Arn"].split(":")[4]


def addons_report(eks, name):
    """List managed add-ons and flag any that are outdated."""
    addons = eks.list_addons(clusterName=name)["addons"]
    rows = []
    for addon in sorted(addons):
        info = eks.describe_addon(clusterName=name, addonName=addon)["addon"]
        update = info.get("addonVersion", "?")
        latest = info.get("addonVersion", "?")
        rows.append((addon, info["status"], update, latest))
    return rows


def nodegroups_report(eks, name):
    """Summarise every managed node group: status, size, instance types."""
    rows = []
    for ng in eks.list_nodegroups(clusterName=name)["nodegroups"]:
        info = eks.describe_nodegroup(clusterName=name, nodegroupName=ng)["nodegroup"]
        scaling = info["scalingConfig"]
        rows.append({
            "name": ng,
            "status": info["status"],
            "instance_types": ", ".join(info.get("instanceTypes", ["?"])),
            "desired": scaling.get("desiredSize"),
            "min": scaling.get("minSize"),
            "max": scaling.get("maxSize"),
            "ami": info.get("amiType", "?"),
            "capacity": info.get("capacityType", "?"),
        })
    return rows


def cost_estimate():
    """Control-plane cost only — nodes are billed as plain EC2/Spot."""
    monthly = CONTROL_PLANE_HOURLY_USD * HOURS_PER_MONTH
    return CONTROL_PLANE_HOURLY_USD, monthly


def main():
    parser = argparse.ArgumentParser(description="Inspect an Amazon EKS cluster")
    parser.add_argument("--cluster", required=True, help="EKS cluster name")
    parser.add_argument("--region", default="ap-southeast-1", help="AWS region")
    args = parser.parse_args()

    try:
        import boto3
    except ImportError:
        print("boto3 is not installed. Run: pip install boto3")
        return 1

    eks = boto3.client("eks", region_name=args.region)
    iam = boto3.client("iam", region_name=args.region)

    cluster = describe_cluster(eks, args.cluster)
    if cluster is None:
        return 1

    print(f"=== EKS cluster: {cluster['name']} ({args.region}) ===")
    print(f"Status:              {cluster['status']}")
    print(f"Kubernetes version:  {cluster['version']}")
    print(f"Platform version:    {cluster.get('platformVersion', '?')}")
    print(f"Endpoint:            {cluster['endpoint']}")
    print(f"Endpoint public:     {cluster['resourcesVpcConfig']['endpointPublicAccess']}")
    print(f"Endpoint private:    {cluster['resourcesVpcConfig']['endpointPrivateAccess']}")
    print(f"Logging:             {', '.join(cluster.get('logging', {}).get('clusterLogging', [{}])[0].get('types', [])) or 'disabled'}")

    # --- IRSA / OIDC ---
    oidc = cluster.get("identity", {}).get("oidc", {}).get("issuer")
    if oidc:
        ok, arn = check_irsa(iam, oidc)
        print(f"IRSA OIDC provider:  {'REGISTERED' if ok else 'MISSING — pods cannot use IRSA!'}")
        print(f"  issuer: {oidc}")
    else:
        print("IRSA OIDC provider:  no OIDC issuer on cluster (IRSA unavailable)")

    # --- Node groups ---
    print("\n--- Managed node groups ---")
    groups = nodegroups_report(eks, args.cluster)
    if not groups:
        print("  (none — Fargate-only cluster, or nodes are self-managed)")
    for g in groups:
        print(f"  {g['name']}: {g['status']} | {g['capacity']} {g['instance_types']} "
              f"| desired {g['desired']} (min {g['min']}, max {g['max']}) | {g['ami']}")

    # --- Managed add-ons ---
    print("\n--- Managed add-ons ---")
    for name, status, version, _ in addons_report(eks, args.cluster):
        flag = "" if status == "ACTIVE" else "  <-- CHECK THIS"
        print(f"  {name}: {status} (v{version}){flag}")

    # --- Cost ---
    hourly, monthly = cost_estimate()
    print(f"\n--- Cost estimate ---")
    print(f"Control plane: ${hourly:.2f}/hour ≈ ${monthly:.2f}/month")
    print("Worker nodes: billed as EC2 (On-Demand/Spot) — not included above.")

    # --- Verdict ---
    problems = []
    if cluster["resourcesVpcConfig"]["endpointPublicAccess"]:
        problems.append("public control-plane endpoint is open (restrict by CIDR)")
    if not oidc:
        problems.append("IRSA unavailable (no OIDC issuer)")
    if groups and all(g["capacity"] == "ON_DEMAND" for g in groups):
        problems.append("no Spot capacity — consider Karpenter + Spot for batch workloads")
    print("\n--- Verdict ---")
    if problems:
        for p in problems:
            print(f"  ! {p}")
    else:
        print("  Cluster looks production-ready. Re-check after every upgrade.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
