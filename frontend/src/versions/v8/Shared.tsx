import { useResources, useSessions, useCreateSession, useUploadResource } from '../../api/hooks';
import { Link, useNavigate } from 'react-router-dom';
import { useState } from 'react';

export function ResourcesPage() {
  const { data } = useResources();
  const res = data?.items || [];
  const upload = useUploadResource();
  const [file, setFile] = useState<File|null>(null);

  const handleUpload = () => {
    if(file) upload.mutate({file}, { onSuccess: () => setFile(null) });
  };

  return (
    <div>
      <h2 className="mb-8">Resource Library</h2>
      <div className="card mb-8 flex flex-col sm:flex-row gap-4">
        <input type="file" onChange={e => setFile(e.target.files?.[0]||null)} className="p-2 border border-gray-300 rounded"/>
        <button onClick={handleUpload} disabled={upload.isPending} className="neo-btn">
          {upload.isPending ? 'Uploading...' : 'Upload Data'}
        </button>
      </div>
      <div className="grid gap-4">
        {res.map((r: any) => (
            <div key={r.id} className="card py-4 flex justify-between items-center">
              <div><strong className="block text-xl">{r.filename}</strong><span className="opacity-70 text-sm">ID: {r.id.slice(0,8)}</span></div>
              <span className="px-3 py-1 bg-opacity-20 bg-green-500 text-green-700 font-bold rounded">{r.status}</span>
            </div>
        ))}
      </div>
    </div>
  );
}

export function SessionsPage() {
  const { data } = useSessions();
  const sessions = data?.items || [];

  return (
    <div>
      <h2 className="mb-8 flex justify-between items-center">
        History 
        <Link to="new"><button className="text-sm px-4 py-2 neo-btn">Start Over</button></Link>
      </h2>
      <div className="grid gap-6">
        {sessions.map((s: any) => (
          <Link to={`/sessions/${s.id}`} key={s.id} className="card block hover:-translate-y-1 transition-transform cursor-pointer">
            <h3 className="text-xl font-bold font-serif mb-2">Session: {s.id.slice(0,12)}</h3>
            <span className="opacity-70 text-sm">Started: {new Date(s.created_at).toLocaleString()}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}

export function NewSessionPage() {
  const { data } = useResources({ status: 'completed' });
  const navigate = useNavigate();
  const create = useCreateSession();
  const [selected, setSelected] = useState("");

  const handleCreate = () => {
    if(selected) create.mutate({resource_id: selected}, {
      onSuccess: (session) => navigate(`../sessions/${session.id}`)
    });
  };

  return (
    <div>
      <h2 className="mb-8">Initialize Session</h2>
      <div className="card max-w-2xl mt-8 flex flex-col gap-6 p-8">
        <label className="font-bold uppercase text-sm tracking-wider">Select Source Material</label>
        <select className="p-4 border border-gray-300 w-full bg-transparent font-medium text-lg outline-none" 
            value={selected} onChange={e=>setSelected(e.target.value)}>
          <option value="">-- Choose Data --</option>
          {data?.items.map(r => <option key={r.id} value={r.id}>{r.filename}</option>)}
        </select>
        <button onClick={handleCreate} disabled={!selected || create.isPending} className="mt-8 py-4 neo-btn text-xl shadow-lg">
          {create.isPending ? 'Waking up the AI...' : 'Engage Tutor'}
        </button>
      </div>
    </div>
  );
}

export function SettingsPage() {
  return (
    <div className="card">
      <h2>Preferences</h2>
      <p className="opacity-70 mt-4">Settings modification temporarily disabled in core system.</p>
    </div>
  )
}
