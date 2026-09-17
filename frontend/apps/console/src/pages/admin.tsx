import { ShieldAlert, UserPlus, Key, Users } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card";
import { Table, TableHeader, TableBody, TableHead, TableRow, TableCell } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { MetricCard } from "@/components/ui/metric-card";

interface TenantMember {
  id: string;
  name: string;
  email: string;
  roles: string[];
  lastActive: string;
}

const MEMBERS: TenantMember[] = [
  {
    id: "usr_1",
    name: "Alex Mercer",
    email: "alex.mercer@jakeai.internal",
    roles: ["admin", "tenant_admin"],
    lastActive: "Now",
  },
  {
    id: "usr_2",
    name: "Sarah Chen",
    email: "sarah.chen@jakeai.internal",
    roles: ["developer", "member"],
    lastActive: "14 mins ago",
  },
  {
    id: "usr_3",
    name: "Marcus Vance",
    email: "marcus.vance@jakeai.internal",
    roles: ["finops_analyst"],
    lastActive: "2 hours ago",
  },
  {
    id: "usr_4",
    name: "Elena Rostova",
    email: "elena.rostova@jakeai.internal",
    roles: ["viewer"],
    lastActive: "Yesterday",
  },
];

export default function AdminPage() {
  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-2xl font-bold tracking-tight">Tenant Administration & RBAC</h1>
            <Badge variant="default" className="text-[10px] font-mono uppercase">
              Admin Restricted
            </Badge>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Manage organization members, role mappings, API tenant secrets, and access policies.
          </p>
        </div>
        <Button size="sm" leftIcon={<UserPlus className="h-4 w-4" />}>
          Invite Member
        </Button>
      </div>

      {/* Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <MetricCard title="Active Members" value="4" icon={Users} />
        <MetricCard title="Tenant Roles Configured" value="5" icon={ShieldAlert} />
        <MetricCard title="Service Tokens" value="2" icon={Key} />
      </div>

      {/* Members Table */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Assigned Tenant Roles</CardTitle>
          <CardDescription>
            Multi-tenant authorization claims validated by FinnApiGo JWT verification.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>User</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Roles</TableHead>
                <TableHead>Last Active</TableHead>
                <TableHead className="text-right">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {MEMBERS.map((m) => (
                <TableRow key={m.id}>
                  <TableCell className="font-semibold">{m.name}</TableCell>
                  <TableCell className="font-mono text-xs text-muted-foreground">{m.email}</TableCell>
                  <TableCell>
                    <div className="flex flex-wrap gap-1">
                      {m.roles.map((r) => (
                        <Badge key={r} variant="secondary" className="font-mono text-[10px]">
                          {r}
                        </Badge>
                      ))}
                    </div>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">{m.lastActive}</TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="sm" className="h-7 text-xs">
                      Edit Roles
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}
