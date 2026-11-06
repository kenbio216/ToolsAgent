import {defineConfig} from 'vite';
export default defineConfig({root:'admin',base:'/boards/equipment-admin/',build:{outDir:'../admin-dist',emptyOutDir:true,target:'es2022'}});
